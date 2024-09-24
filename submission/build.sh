#!/usr/bin/env bash
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

sudo docker build -t surgvu_cat2 "$SCRIPTPATH"
