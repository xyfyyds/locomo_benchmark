import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os, json
from tqdm import tqdm
import argparse
from global_methods import set_openai_key, set_anthropic_key, set_gemini_key
from task_eval.evaluation import eval_question_answering
from task_eval.evaluation_stats import analyze_aggr_acc
from task_eval.gpt_utils import get_gpt_answers
from task_eval.claude_utils import get_claude_answers
from task_eval.gemini_utils import get_gemini_answers
from task_eval.hf_llm_utils import init_hf_model, get_hf_answers

import numpy as np
import google.generativeai as genai

def parse_args():

    parser = argparse.ArgumentParser()
    parser.add_argument('--out-file', required=True, type=str)
    parser.add_argument('--model', required=True, type=str)
    parser.add_argument('--data-file', type=str, required=True)
    parser.add_argument('--use-rag', action="store_true")
    parser.add_argument('--use-4bit', action="store_true", default=False)
    parser.add_argument('--batch-size', default=1, type=int)
    parser.add_argument('--rag-mode', type=str, default="")
    parser.add_argument('--emb-dir', type=str, default="")
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--retriever', type=str, default="contriever")
    parser.add_argument('--overwrite', action="store_true")
    args = parser.parse_args()
    return args


def main():

    # get arguments
    args = parse_args()

    print("******************  Evaluating Model %s ***************" % args.model)

    if 'gpt' in args.model:
        # set openai API key
        set_openai_key()

    elif 'claude' in args.model:
        # set openai API key
        set_anthropic_key()

    elif 'gemini' in args.model:
        # set openai API key
        set_gemini_key()
        if args.model == "gemini-pro-1.0":
            model_name = "models/gemini-1.0-pro-latest"

        gemini_model = genai.GenerativeModel(model_name)
    
    elif any([model_name in args.model for model_name in ['gemma', 'llama', 'mistral', 'Qwen']]):
        hf_pipeline, hf_model_name = init_hf_model(args)

    else:
        raise NotImplementedError


    # load conversations
    samples = json.load(open(args.data_file))
    prediction_key = "%s_prediction" % args.model if not args.use_rag else "%s_%s_top_%s_prediction" % (args.model, args.rag_mode, args.top_k)
    model_key = "%s" % args.model if not args.use_rag else "%s_%s_top_%s" % (args.model, args.rag_mode, args.top_k)
    # load the output file if it exists to check for overwriting
    if os.path.exists(args.out_file):
        out_samples = {d['sample_id']: d for d in json.load(open(args.out_file))}
    else:
        out_samples = {}


    for data in samples:

        out_data = {'sample_id': data['sample_id']}
        if data['sample_id'] in out_samples:
            out_data['qa'] = out_samples[data['sample_id']]['qa'].copy()
        else:
            out_data['qa'] = data['qa'].copy()

        if 'gpt' in args.model:
            # get answers for each sample
            answers = get_gpt_answers(data, out_data, prediction_key, args)
        elif 'claude' in args.model:
            answers = get_claude_answers(data, out_data, prediction_key, args)
        elif 'gemini' in args.model:
            answers = get_gemini_answers(gemini_model, data, out_data, prediction_key, args)
        elif any([model_name in args.model for model_name in ['gemma', 'llama', 'mistral', 'Qwen']]):
            answers = get_hf_answers(data, out_data, args, hf_pipeline, hf_model_name)
        else:
            raise NotImplementedError

        # evaluate individual QA samples and save the score
        exact_matches, lengths, recall = eval_question_answering(answers['qa'], prediction_key)
        for i in range(0, len(answers['qa'])):
            answers['qa'][i][model_key + '_f1'] = round(exact_matches[i], 3)
            if args.use_rag and len(recall) > 0:
                answers['qa'][i][model_key + '_recall'] = round(recall[i], 3)

        out_samples[data['sample_id']] = answers


    with open(args.out_file, 'w') as f:
        json.dump(list(out_samples.values()), f, indent=2)

    
    analyze_aggr_acc(args.data_file, args.out_file, args.out_file.replace('.json', '_stats.json'),
                model_key, model_key + '_f1', rag=args.use_rag)
    # encoder=tiktoken.encoding_for_model(args.model))


main()

