import argparse
import time
import math
import random

import torch

import smm_lstm_models
import vocab
import language_model
import split_corpus_dataset
import ivec_appenders
import smm_ivec_extractor

from runtime_utils import CudaStream, init_seeds, filelist_to_tokenized_splits
from runtime_multifile import train, evaluate, BatchFilter

from loggers import InfinityLogger
import numpy as np


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PyTorch RNN/LSTM Language Model')
    parser.add_argument('--train-list', type=str, required=True,
                        help='file with paths to training documents')
    parser.add_argument('--valid-list', type=str, required=True,
                        help='file with paths to validation documents')
    parser.add_argument('--test-list', type=str, required=True,
                        help='file with paths to testin documents')
    parser.add_argument('--lr', type=float, default=20,
                        help='initial learning rate')
    parser.add_argument('--beta', type=float, default=0,
                        help='L2 regularization penalty')
    parser.add_argument('--clip', type=float, default=0.25,
                        help='gradient clipping')
    parser.add_argument('--epochs', type=int, default=40,
                        help='upper epoch limit')
    parser.add_argument('--batch_size', type=int, default=20, metavar='N',
                        help='batch size')
    parser.add_argument('--bptt', type=int, default=35,
                        help='sequence length')
    parser.add_argument('--seed', type=int, default=1111,
                        help='random seed')
    parser.add_argument('--cuda', action='store_true',
                        help='use CUDA')
    parser.add_argument('--concat-articles', action='store_true',
                        help='pass hidden states over article boundaries')
    parser.add_argument('--min-batch-size', type=int, default=1,
                        help='stop, once batch is smaller than given size')
    parser.add_argument('--log-interval', type=int, default=200, metavar='N',
                        help='report interval')
    parser.add_argument('--ivec-extractor', type=str, required=True,
                        help='where to load a ivector extractor from')
    parser.add_argument('--ivec-randomness', type=float, required=True,
                        help='log_10 of +/- boundary of uniform, from which the ivectors are drawn')
    parser.add_argument('--load', type=str, required=True,
                        help='where to load a model from')
    parser.add_argument('--save', type=str,  required=True,
                        help='path to save the final model')
    args = parser.parse_args()
    print(args)

    init_seeds(args.seed, args.cuda)

    print("loading LSTM model...")
    with open(args.load, 'rb') as f:
        lm = language_model.load(f)
    vocab = lm.vocab
    model = lm.model
    print(model)

    print("loading SMM iVector extractor ...")
    with open(args.ivec_extractor, 'rb') as f:
        ivec_extractor = smm_ivec_extractor.load(f)
    ivec_extractor._nb_iters = args.ivec_randomness
    print(ivec_extractor)

    print("preparing data...")
    ivec_app_creator = lambda ts: ivec_appenders.CheatingIvecAppender(ts, ivec_extractor)

    print("\ttraining...")
    train_tss = filelist_to_tokenized_splits(args.train_list, vocab, args.bptt)

    print("\tvalidation...")
    valid_tss = filelist_to_tokenized_splits(args.valid_list, vocab, args.bptt)
    valid_data = split_corpus_dataset.BatchBuilder([ivec_app_creator(ts) for ts in valid_tss], args.batch_size,
                                                   discard_h=not args.concat_articles)
    if args.cuda:
        valid_data = CudaStream(valid_data)

    print("\ttesting...")
    test_tss = filelist_to_tokenized_splits(args.test_list, vocab, args.bptt)
    test_data = split_corpus_dataset.BatchBuilder([ivec_app_creator(ts) for ts in test_tss], args.batch_size,
                                                   discard_h=not args.concat_articles)
    if args.cuda:
        test_data = CudaStream(test_data)


    print("training...")
    lr = args.lr
    best_val_loss = None

    # At any point you can hit Ctrl + C to break out of training early.
    try:
        for epoch in range(1, args.epochs+1):
            epoch_start_time = time.time()

            train_data_ivecs = [ivec_app_creator(ts) for ts in train_tss]
            random.shuffle(train_data_ivecs)
            train_data = split_corpus_dataset.BatchBuilder(
                train_data_ivecs, 
                args.batch_size, discard_h=not args.concat_articles
            )
            if args.cuda:
                train_data = CudaStream(train_data)

            logger = InfinityLogger(epoch, args.log_interval, lr)
            train_data_filtered = BatchFilter(
                train_data, args.batch_size, args.bptt, args.min_batch_size
            )

            optim = torch.optim.SGD(model.parameters(), lr=lr, weight_decay=args.beta)
            
            train(
                lm, train_data_filtered, optim, logger, 
                batch_size=args.batch_size, 
                clip=args.clip, cuda=args.cuda
            )
            train_data_filtered.report()

            val_loss = evaluate(lm, valid_data, args.batch_size, args.cuda)
            print('-' * 89)
            print('| end of epoch {:3d} | time: {:5.2f}s | # updates: {} | valid loss {:5.2f} | '
                    'valid ppl {:8.2f}'.format(epoch, logger.time_since_creation(), logger.nb_updates(),
                                               val_loss, math.exp(val_loss)))
            print('-' * 89)
            # Save the model if the validation loss is the best we've seen so far.
            if not best_val_loss or val_loss < best_val_loss:
                with open(args.save, 'wb') as f:
                    lm.save(f)
                best_val_loss = val_loss
            else:
                lr /= 2.0
                pass

    except KeyboardInterrupt:
        print('-' * 89)
        print('Exiting from training early')

    # Load the best saved model.
    with open(args.save, 'rb') as f:
        lm = language_model.load(f)
    vocab = lm.vocab
    model = lm.model

    # Run on test data.
    test_loss = evaluate(lm, test_data, args.batch_size, args.cuda)
    print('=' * 89)
    print('| End of training | test loss {:5.2f} | test ppl {:8.2f}'.format(
        test_loss, math.exp(test_loss)))
    print('=' * 89)