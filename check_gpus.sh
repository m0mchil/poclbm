#!/bin/bash

MINERD=/home/brock/poclbm-fork/poclbm
LOGFILE=$MINERD/last.log
ALL_GPUS="0 1 3 4"

ALIVE_GPUS=`tail -10 $LOGFILE | sed 's/^.*Device\[\([0-9]\)\].*$/\1/g' | sort | uniq`
ALIVE_GPUS=`echo $ALIVE_GPUS`

if [ "$ALIVE_GPUS" != "$ALL_GPUS" ]; then
    echo "GPU Missing! We have $ALIVE_GPUS." | mail -s "Bitcoin Miner Alert" brock@brocktice.com
fi
