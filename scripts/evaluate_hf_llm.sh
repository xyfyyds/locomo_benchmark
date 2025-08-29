# sets necessary environment variables
# source scripts/env.sh


# run models

python3 task_eval/evaluate_qa.py \
    --data-file ./data/locomo10.json --out-file ./outputs/locomo10_qa.json \
    --model ../models/Qwen/Qwen2.5-3B-Instruct --batch-size 1

