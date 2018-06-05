import argparse
import math
import torch

from data_pipeline.data import tokens_from_fn
from data_pipeline.multistream import batchify
from data_pipeline.temporal_splitting import TemporalSplits
from language_models import language_model

from runtime_utils import TransposeWrapper, init_seeds
from runtime_multifile import evaluate_, train_

from loggers import ProgressLogger


def epoch_summary(epoch_no, nb_updates, elapsed_time, loss):
    delim_line = '-' * 89 + '\n'

    epoch_stmt = 'end of epoch {:3d}'.format(epoch)
    updates_stmt = '# updates: {}'.format(nb_updates)
    time_stmt = 'time: {:5.2f}s'.format(elapsed_time)
    loss_stmt = 'valid loss {:5.2f}'.format(loss)
    ppl_stmt = 'valid ppl {:8.2f}'.format(math.exp(loss))
    values_line = '| {} | {} | {} | {} | {}\n'.format(
        epoch_stmt, updates_stmt, time_stmt, loss_stmt, ppl_stmt
    )

    return delim_line + values_line + delim_line


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PyTorch RNN/LSTM Language Model')
    parser.add_argument('--train', type=str, required=True,
                        help='location of the train corpus')
    parser.add_argument('--valid', type=str, required=True,
                        help='location of the valid corpus')
    parser.add_argument('--characters', action='store_true',
                        help='work on character level, whitespace is significant')
    parser.add_argument('--shuffle-lines', action='store_true',
                        help='shuffle lines before every epoch')

    parser.add_argument('--batch_size', type=int, default=20, metavar='N',
                        help='batch size')
    parser.add_argument('--bptt', type=int, default=35,
                        help='sequence length')

    parser.add_argument('--lr', type=float, default=20,
                        help='initial learning rate')
    parser.add_argument('--beta', type=float, default=0,
                        help='L2 regularization penalty')
    parser.add_argument('--clip', type=float, default=0.25,
                        help='gradient clipping')
    parser.add_argument('--epochs', type=int, default=40,
                        help='upper epoch limit')

    parser.add_argument('--seed', type=int, default=1111,
                        help='random seed')
    parser.add_argument('--cuda', action='store_true',
                        help='use CUDA')
    parser.add_argument('--log-interval', type=int, default=200, metavar='N',
                        help='report interval')
    parser.add_argument('--load', type=str, required=True,
                        help='where to load a model from')
    parser.add_argument('--save', type=str, required=True,
                        help='path to save the final model')
    args = parser.parse_args()
    print(args)

    init_seeds(args.seed, args.cuda)

    print("loading model...")
    with open(args.load, 'rb') as f:
        lm = language_model.load(f)
    if args.cuda:
        lm.model.cuda()
    print(lm.model)

    print("preparing data...")
    tokenize_regime = 'words'
    if args.characters:
        tokenize_regime = 'chars'

    train_ids = tokens_from_fn(args.train, lm.vocab, randomize=False, regime=tokenize_regime)
    train_batched = batchify(train_ids, args.batch_size, args.cuda)
    train_data_tb = TemporalSplits(
        train_batched,
        nb_inputs_necessary=lm.model.in_len,
        nb_targets_parallel=args.bptt
    )
    train_data = TransposeWrapper(train_data_tb)

    valid_ids = tokens_from_fn(args.valid, lm.vocab, randomize=False, regime=tokenize_regime)
    valid_batched = batchify(valid_ids, 10, args.cuda)
    valid_data_tb = TemporalSplits(
        valid_batched,
        nb_inputs_necessary=lm.model.in_len,
        nb_targets_parallel=args.bptt
    )
    valid_data = TransposeWrapper(valid_data_tb)

    print("training...")
    lr = args.lr
    best_val_loss = None

    for epoch in range(1, args.epochs+1):
        logger = ProgressLogger(epoch, args.log_interval, lr, len(train_batched)//args.bptt)
        optim = torch.optim.SGD(lm.model.parameters(), lr, weight_decay=args.beta)

        train_(
            lm.model, train_data, optim,
            logger, args.clip,
            use_ivecs=False,
            custom_batches=False,
        )

        val_loss = evaluate_(
            lm.model, valid_data,
            use_ivecs=False,
            custom_batches=False,
        )
        print(epoch_summary(epoch, logger.nb_updates(), logger.time_since_creation(), val_loss))

        # Save the model if the validation loss is the best we've seen so far.
        if not best_val_loss or val_loss < best_val_loss:
            with open(args.save, 'wb') as f:
                lm.save(f)
            best_val_loss = val_loss
        else:
            lr /= 2.0
            pass
