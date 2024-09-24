#!/usr/bin/env bash

bash build.sh

sudo docker save surgvu_cat2 | gzip -c > surgvu_teambcu_baseline.tar.gz
