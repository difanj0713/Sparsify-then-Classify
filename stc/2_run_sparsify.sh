#!/bin/bash
set -e

models=("distilbert") # "roberta" "gpt2" "gpt2-medium" "gpt2-large" "gpt2-xl")
datasets=("imdb") # "edos" "sst-2")
finetuned=0

for model in "${models[@]}"; do
    for dataset in "${datasets[@]}"; do
        echo "Starting layer-wise probe for model ${model} over dataset ${dataset}..."
        output_path="../dataset_acts/${dataset}/performance"
        mkdir -p ${output_path}
        python3 sparsify.py --model_name ${model} --dataset ${dataset} --is_finetuned ${finetuned}
    done
done