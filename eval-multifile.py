import argparse
import math
import torch
import torch.nn as nn

import model
import lstm_model
import vocab
import language_model
import split_corpus_dataset
from hidden_state_reorganization import HiddenStateReorganizer

from runtime_utils import CudaStream, init_seeds, filelist_to_tokenized_splits
from runtime_multifile import evaluate

import numpy as np


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
    args = parser.parse_args()
    print(args)

    init_seeds(args.seed, args.cuda)

    print("loading model...")
    with open(args.load, 'rb') as f:
        lm = language_model.load(f)
    vocab = lm.vocab
    model = lm.model
    print(model)

    print("preparing data...")
    ivec_eetor = lambda x: np.asarray([sum(x) % 1337])
    ivec_app_creator = lambda ts: split_corpus_dataset.CheatingIvecAppender(ts, ivec_eetor)

    tss = filelist_to_tokenized_splits(args.file_list, vocab, args.bptt)
    data = split_corpus_dataset.BatchBuilder(tss, ivec_app_creator, args.batch_size,
                                               discard_h=not args.concat_articles)
    if args.cuda:
        data = CudaStream(data)

    criterion = nn.NLLLoss()

    loss = evaluate(lm, data, args.batch_size, args.cuda, use_ivecs=False)
    print('loss {:5.2f} | ppl {:8.2f}'.format( loss, math.exp(loss)))
