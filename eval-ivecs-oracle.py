import argparse
import math
import torch

import model
import lstm_model
import vocab
import language_model
import ivec_appenders
import split_corpus_dataset
import smm_ivec_extractor

from runtime_utils import CudaStream, filelist_to_tokenized_splits, init_seeds
from runtime_multifile import evaluate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PyTorch RNN/LSTM Language Model')
    parser.add_argument('--file-list', type=str, required=True,
                        help='file with paths to training documents')
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
    parser.add_argument('--load', type=str, required=True,
                        help='where to load a model from')
    parser.add_argument('--ivec-extractor', type=str, required=True,
                        help='where to load a ivector extractor from')
    parser.add_argument('--ivec-nb-iters', type=int, 
                        help='override the number of iterations when extracting ivectors')
    args = parser.parse_args()
    print(args)

    init_seeds(args.seed, args.cuda)

    print("loading LM...")
    with open(args.load, 'rb') as f:
        lm = language_model.load(f)
    print(lm.model)

    print("loading SMM iVector extractor ...")
    with open(args.ivec_extractor, 'rb') as f:
        ivec_extractor = smm_ivec_extractor.load(f)
    if args.ivec_nb_iters:
        ivec_extractor._nb_iters = args.ivec_nb_iters
    print(ivec_extractor)

    print("preparing data...")
    ivec_app_creator = lambda ts: ivec_appenders.CheatingIvecAppender(ts, ivec_extractor)

    tss = filelist_to_tokenized_splits(args.file_list, lm.vocab, args.bptt)
    tss_ivecs = [ivec_app_creator(ts) for ts in tss]
    data = split_corpus_dataset.BatchBuilder(tss_ivecs, args.batch_size, discard_h=not args.concat_articles)

    if args.cuda:
        data = CudaStream(data)

    loss = evaluate(lm, data, args.batch_size, args.cuda)
    print('loss {:5.2f} | ppl {:8.2f}'.format( loss, math.exp(loss)))