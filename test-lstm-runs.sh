#!/usr/bin/env bash
EXP_DIR=$1
EXP_NAME=$2
DATA_ROOT=$3

python build_lstm.py \
    --wordlist=$DATA_ROOT/wordlist.txt \
    --unk="<unk>" \
    --emsize=20 \
    --nhid=20 \
    --save=$EXP_DIR/$EXP_NAME.init.lm


# 1) train and test in the traditional setup
python train.py \
    --data=$DATA_ROOT/pythlm-symlinks-no-train \
    --cuda \
    --epochs=1 \
    --load=$EXP_DIR/$EXP_NAME.init.lm \
    --save=$EXP_DIR/$EXP_NAME.lm

python eval.py \
    --data=$DATA_ROOT/pythlm-symlinks-no-train \
    --cuda \
    --load=$EXP_DIR/$EXP_NAME.lm


# 2) train and test using multifile setup
python train-multifile.py \
    --train-list=$DATA_ROOT/valid-list.txt \
    --valid-list=$DATA_ROOT/test-list.txt \
    --test-list=$DATA_ROOT/valid-list.txt \
    --cuda \
    --epochs=1 \
    --load=$EXP_DIR/$EXP_NAME.init.lm \
    --save=$EXP_DIR/$EXP_NAME-mf.lm

python eval-multifile.py \
    --file-list=$DATA_ROOT/test-list.txt \
    --cuda \
    --load=$EXP_DIR/$EXP_NAME-mf.lm