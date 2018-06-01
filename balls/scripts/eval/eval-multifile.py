import argparse
import math

from language_models import language_model
from data_pipeline.multistream import BatchBuilder

from data_pipeline.temporal_splitting import TemporalSplits
from split_corpus_dataset import TokenizedSplitFFBase
from runtime_utils import CudaStream, init_seeds, filelist_to_objects
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
    temp_split_builder = lambda seq: TemporalSplits(seq, lm.model.in_len, args.bptt)
    ts_builder = lambda f: TokenizedSplitFFBase(f, lm.vocab, temp_split_builder)

    tss = filelist_to_objects(args.file_list, ts_builder)
    data = BatchBuilder(tss, args.batch_size,
                        discard_h=not args.concat_articles)
    if args.cuda:
        data = CudaStream(data)

    loss = evaluate(lm.model, data, use_ivecs=False)
    print('loss {:5.2f} | ppl {:8.2f}'.format(loss, math.exp(loss)))