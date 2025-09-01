import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import random
import os, json
from tqdm import tqdm
from transformers import AutoTokenizer
import transformers
import torch
import huggingface_hub

from task_eval.rag_utils import build_bm25s_index_from_data, bm25s_retrieve_topk

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)
import torch
import huggingface_hub


MAX_LENGTH={'llama2': 4096,
            'llama2-70b': 4096,
            'llama2-chat': 4096,
            'llama2-chat-70b': 4096,
            'llama3-chat-70b': 4096,
            'gpt-3.5-turbo-16k': 16000,
            'gpt-3.5-turbo': 4096,
            'gemma-7b-it': 8000,
            'mistral-7b-128k': 128000,
            'mistral-7b-4k': 4096,
            'mistral-7b-8k': 8000,
            'mistral-instruct-7b-4k': 4096,
            'mistral-instruct-7b-8k': 8000,
            'mistral-instruct-7b-32k-v2': 8000,
            'mistral-instruct-7b-8k-new': 8000,
            'mistral-instruct-7b-32k': 32000,
            'mistral-instruct-7b-128k': 128000,
            'qwen-7b': 8192,
            'qwen2.5-3b-instruct': 8192
            }


QA_PROMPT = """
Based on the above conversations, write a short answer for the following question in a few words. Do not write complete and lengthy sentences. Answer with exact words from the conversations whenever possible.

Question: {}
"""

# QA_PROMPT_BATCH = """
# Based on the above conversations, answer the following questions in a few words. Write the answers as a list of strings in the json format. Start and end with a square bracket.

# """

QA_PROMPT_BATCH = """
Based on the above conversations, write short answers for each of the following questions in a few words. Write the answers in the form of a json dictionary where each entry contains the question number as 'key' and the short answer as value. Answer with exact words from the conversations whenever possible.

"""

LLAMA2_CHAT_SYSTEM_PROMPT = """
<s>[INST] <<SYS>>
You are a helpful, respectful and honest assistant whose job is to understand the following conversation and answer questions based on the conversation.
If you don't know the answer to a question, please don't share false information.
<</SYS>>

{} [/INST]
"""


LLAMA3_CHAT_SYSTEM_PROMPT = """
<s>[INST] <<SYS>>
You are a helpful, respectful and honest assistant whose job is to understand the following conversation and answer questions based on the conversation.
If you don't know the answer to a question, please don't share false information.
<</SYS>>

{} [/INST]
"""


MISTRAL_INSTRUCT_SYSTEM_PROMPT = """
<s>[INST] {} [/INST]
"""

GEMMA_INSTRUCT_PROMPT = """
<bos><start_of_turn>user
{}<end_of_turn>
"""

CONV_START_PROMPT = "Below is a conversation between two people: {} and {}. The conversation takes place over multiple days and the date of each conversation is wriiten at the beginning of the conversation.\n\n"

ANS_TOKENS_PER_QUES = 50


def run_mistral(pipeline, question, data, tokenizer, args):

    question_prompt =  QA_PROMPT.format(question)
    query_conv = get_input_context(data['conversation'], MISTRAL_INSTRUCT_SYSTEM_PROMPT.format(question_prompt), tokenizer, args)

    # without chat_template
    # query = MISTRAL_INSTRUCT_SYSTEM_PROMPT.format(query_conv + '\n\n' + question_prompt)
    # with chat template
    query = tokenizer.apply_chat_template([{"role": "user", "content": query_conv + '\n\n' + question_prompt}], tokenize=False, add_generation_prompt=True)

    sequences = pipeline(
                        query,
                        # max_length=8000,
                        max_new_tokens=args.batch_size*ANS_TOKENS_PER_QUES,
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                        do_sample=True,
                        top_k=10,
                        temperature=0.4,
                        top_p=0.9,
                        return_full_text=False,
                        num_return_sequences=1,
                        )
    return sequences[0]['generated_text']


def run_gemma(pipeline, question, data, tokenizer, args):

    question_prompt =  QA_PROMPT.format(question)
    query_conv = get_input_context(data['conversation'], GEMMA_INSTRUCT_PROMPT.format(question_prompt), tokenizer, args)

    # without chat_template
    # query = MISTRAL_INSTRUCT_SYSTEM_PROMPT.format(query_conv + '\n\n' + question_prompt)
    # with chat template
    query = tokenizer.apply_chat_template([{"role": "user", "content": query_conv + '\n\n' + question_prompt}], tokenize=False, add_generation_prompt=True)

    sequences = pipeline(
                        query,
                        # max_length=8000,
                        max_new_tokens=args.batch_size*ANS_TOKENS_PER_QUES,
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                        do_sample=True,
                        top_k=10,
                        temperature=0.4,
                        top_p=0.9,
                        return_full_text=False,
                        num_return_sequences=1,
                        )
    return sequences[0]['generated_text']


def run_llama(pipeline, question, data, tokenizer, args):

    question_prompt =  QA_PROMPT.format(question)
    query_conv = get_input_context(data['conversation'], LLAMA3_CHAT_SYSTEM_PROMPT.format(question_prompt), tokenizer, args)

    # without chat_template
    # query = MISTRAL_INSTRUCT_SYSTEM_PROMPT.format(query_conv + '\n\n' + question_prompt)
    # with chat template
    query = tokenizer.apply_chat_template([{"role": "system", "content": "You are a helpful, respectful and honest assistant whose job is to understand the following conversation and answer questions based on the conversation. If you don't know the answer to a question, please don't share false information."},
                                           {"role": "user", "content": query_conv + '\n\n' + question_prompt}], tokenize=False, add_generation_prompt=True)

    sequences = pipeline(
                        query,
                        # max_length=8000,
                        max_new_tokens=args.batch_size*ANS_TOKENS_PER_QUES,
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                        do_sample=True,
                        top_k=10,
                        temperature=0.4,
                        top_p=0.9,
                        return_full_text=False,
                        num_return_sequences=1,
                        )
    return sequences[0]['generated_text']


def get_chatgpt_summaries(ann_file):

    data = json.load(open(ann_file))
    conv = ''
    for i in range(1,20):
        if 'session_%s' % i in data:
            conv = conv + data['session_%s_date_time' % i] + '\n'
            for dialog in data['session_%s' % i]:
                conv = conv + dialog['speaker'] + ': ' + dialog['clean_text'] + '\n'


def get_input_context(data, question_prompt, encoding, args):

    # get number of tokens from question prompt
    question_tokens = len(encoding.encode(question_prompt))

    # start instruction prompt
    speakers_names = list(set([d['speaker'] for d in data['session_1']]))
    start_prompt = CONV_START_PROMPT.format(speakers_names[0], speakers_names[1])
    start_tokens = len(encoding.encode(start_prompt))

    query_conv = ''
    total_tokens = 0
    min_session = -1
    stop = False
    session_nums = [int(k.split('_')[-1]) for k in data.keys() if 'session' in k and 'date_time' not in k]
    for i in range(min(session_nums), max(session_nums) + 1):
        if 'session_%s' % i in data:
            for dialog in data['session_%s' % i][::-1]:
                turn = ''
                turn = dialog['speaker'] + ' said, \"' + dialog['text'] + '\"' + '\n'
                if "blip_caption" in dialog:
                    turn += ' and shared %s.' % dialog["blip_caption"]
                turn += '\n'

                # get an approximate estimate of where to truncate conversation to fit into contex window
                dynamic_max_len = getattr(encoding, "model_max_length", 4096)
                new_tokens = len(encoding.encode('DATE: ' + data['session_%s_date_time' % i] + '\n' + 'CONVERSATION:\n' + turn))
                if (start_tokens + new_tokens + total_tokens + question_tokens) < (dynamic_max_len-(ANS_TOKENS_PER_QUES*args.batch_size)): # if new turns still fit into context window, add to query
                    query_conv = turn + query_conv
                    total_tokens += len(encoding.encode(turn))
                else:
                    min_session = i
                    stop = True
                    break

            query_conv = '\nDATE: ' + data['session_%s_date_time' % i] + '\n' + 'CONVERSATION:\n' + query_conv
        
        if stop:
            break
    
    query_conv = start_prompt + query_conv

    return query_conv


def get_hf_answers(in_data, out_data, args, pipeline, model_name):

    # 与 evaluate_qa.py 保持一致，否则统计用不到 RAG 的 key
    if args.use_rag:
        prediction_key = f"{args.model}_{args.rag_mode}_top_{args.top_k}_prediction"
        model_key = f"{args.model}_{args.rag_mode}_top_{args.top_k}"
    else:
        prediction_key = f"{args.model}_prediction"
        model_key = f"{args.model}"


    if 'mistral' in model_name:
        encoding = AutoTokenizer.from_pretrained(model_name)
    else:
        encoding = AutoTokenizer.from_pretrained(model_name)

    for batch_start_idx in range(0, len(in_data['qa']) + args.batch_size, args.batch_size):

        questions = []
        include_idxs = []
        cat_5_idxs = []
        cat_5_answers = []
        for i in range(batch_start_idx, batch_start_idx + args.batch_size):

            # end if all questions have been included
            if i>=len(in_data['qa']):
                break
            qa = in_data['qa'][i]
            # # skip if already predicted and overwrite is set to False
            # if '%s_prediction' % args.model not in qa or args.overwrite:
            #     include_idxs.append(i)
            # else:
            #     print("Skipping -->", qa['question'])
            #     continue
            # # skip if already predicted and overwrite is set to False
            if (prediction_key not in qa) or args.overwrite:
                include_idxs.append(i)
            else:
                print("Skipping -->", qa['question'])
                continue

            # pre-processing steps for Temporal (2) and Adversarial (5) categories
            if qa['category'] == 2:
                questions.append(qa['question'] + ' Use DATE of CONVERSATION to answer with an approximate date.')
            elif qa['category'] == 5:
                question = qa['question'] + " (a) {} (b) {}. Select the correct answer by writing (a) or (b)."
                if random.random() < 0.5:
                    if qa.get('answer') is not None:
                        question = question.format('No information available', qa['answer'])
                        answer = {'a': 'No information available', 'b': qa['answer']}
                    else:
                        question = question.format('No information available', qa['adversarial_answer'])
                        answer = {'a': 'No information available', 'b': qa['adversarial_answer']}
                else:
                    if qa.get('answer') is not None:
                        question = question.format(qa['answer'], 'No information available')
                        answer = {'b': 'No information available', 'a': qa['answer']}
                    else:
                        question = question.format(qa['adversarial_answer'], 'No information available')
                        answer = {'b': 'No information available', 'a': qa['adversarial_answer']}
                cat_5_idxs.append(len(questions))
                questions.append(question)
                cat_5_answers.append(answer)
                # questions.append(qa['question'] + " Write NOT ANSWERABLE if the question cannot be answered.")
            else:
                questions.append(qa['question'])

        if questions == []:
            continue


        if args.batch_size == 1:

            raw_question = questions[0]
            q_for_model = raw_question
            ctx_ids = []

            # 2) RAG：bm25/bm25s 上下文拼接
            if args.use_rag and args.retriever and args.retriever.lower() in ['bm25', 'bm25s']:
                method = getattr(args, "bm25_method", "lucene")  # 'lucene'/'bm25+'/'bm25l'/'atire'/'robertson'
                retr, doc_texts, doc_ids = build_bm25s_index_from_data(in_data['conversation'], method=method)
                # bm25s: 先 index(tokenize(corpus))，再 retrieve(tokenize(query), k) :contentReference[oaicite:0]{index=0}
                top_ctx = bm25s_retrieve_topk(retr, raw_question, doc_texts, doc_ids, args.top_k)
                ctx_ids = [c.get("id", "") for c in top_ctx]
                ctx_block = "Here are retrieved contexts related to the question: \n{}\n\n".format(
                    args.top_k, "\n".join(c.get("text", "") for c in top_ctx)
                ) + "Based on the above context, answer the following question."
                q_for_model = ctx_block + raw_question

            if 'mistral' in model_name:
                answer = run_mistral(pipeline, q_for_model, in_data, encoding, args)
            elif 'llama' in model_name:
                answer = run_llama(pipeline, q_for_model, in_data, encoding, args)
            elif 'gemma' in model_name:
                answer = run_gemma(pipeline, q_for_model, in_data, encoding, args)
            elif 'Qwen' in model_name:
                answer = run_llama(pipeline, q_for_model, in_data, encoding, args)
            else:
                raise NotImplementedError
            
            print(q_for_model, answer)

            # post process answers, necessary for Adversarial Questions
            answer = answer.replace('\\"', "'").strip()
            answer = [w.strip() for w in answer.split('\n') if not w.strip().isspace()][0]
            if len(cat_5_idxs) > 0:
                answer = answer.lower().strip()
                if '(a)' in answer:
                    answer = cat_5_answers[0]['a']
                else:
                    answer = cat_5_answers[0]['b']
            else:
                answer = answer.lower().replace('(a)', '').replace('(b)', '').replace('a)', '').replace('b)', '').replace('answer:', '').strip()
            out_data['qa'][batch_start_idx][prediction_key] = answer
            if args.use_rag:
                out_data['qa'][batch_start_idx][prediction_key + "_context"] = ctx_ids

        else:            
            raise NotImplementedError

    return out_data


def init_hf_model(args):

    if args.model == 'llama2':
        model_name = "meta-llama/Llama-2-7b-hf"

    elif args.model == 'llama2-70b':
        model_name = "meta-llama/Llama-2-70b-hf"

    elif args.model == 'llama2-chat':
        model_name = "meta-llama/Llama-2-7b-chat-hf"

    elif args.model == 'llama2-chat-70b':
        model_name = "meta-llama/Llama-2-70b-chat-hf"

    elif args.model == 'llama3-chat-70b':
        model_name = "meta-llama/Meta-Llama-3-70B-Instruct"

    elif args.model in ['mistral-7b-128k', 'mistral-7b-4k', 'mistral-7b-8k']:
        model_name = "mistralai/Mistral-7B-v0.1"

    elif args.model in ['mistral-instruct-7b-128k', 'mistral-instruct-7b-8k', 'mistral-instruct-7b-12k']:
        model_name = "mistralai/Mistral-7B-Instruct-v0.1"

    elif args.model in ['mistral-instruct-7b-8k-new']:
        model_name = "mistralai/Mistral-7B-Instruct-v0.1"
    
    elif args.model in ['mistral-instruct-7b-32k-v2']:
        model_name = "mistralai/Mistral-7B-Instruct-v0.2"
    
    elif args.model in ['gemma-7b-it']:
        model_name = 'google/gemma-7b-it'

    elif 'mistral' in args.model.lower():
        model_name = 'mistralai/' + args.model

    elif 'qwen' in args.model.lower():
        model_name = args.model

    else:
        raise ValueError

    hf_token = os.environ.get('HF_TOKEN', None)

    if hf_token:
        huggingface_hub.login(hf_token)

    if args.use_4bit:

        try:
            import torch_npu  # noqa
            print("NPU detected -> disabling --use-4bit (not supported on NPU).")
            args.use_4bit = False
        except Exception:
            pass

        print("Using 4-bit inference")
        tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token)
        tokenizer.pad_token_id = tokenizer.eos_token_id    # for open-ended generation

        if 'gemma' in args.model:
            bnb_config = BitsAndBytesConfig(load_in_4bit=True,
                                            bnb_4bit_compute_dtype=torch.float16)
        else:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )

        if 'mistralai' in model_name:
            if 'v0.1' in model_name:
                model = AutoModelForCausalLM.from_pretrained(model_name, 
                                                            torch_dtype=torch.float16, 
                                                            attn_implementation="flash_attention_2",
                                                            quantization_config=bnb_config,
                                                            device_map="auto",
                                                            trust_remote_code=True,)
            else:
                model = AutoModelForCausalLM.from_pretrained(model_name,
                                                            quantization_config=bnb_config,
                                                            device_map="auto",
                                                            trust_remote_code=True)
        
        else:
            model = AutoModelForCausalLM.from_pretrained(model_name, 
                                            torch_dtype=torch.float16,
                                            quantization_config=bnb_config,
                                            device_map="auto",
                                            trust_remote_code=True,)

        pipeline = transformers.pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            trust_remote_code=True,
            device_map="auto",    # finds GPU
        )
    
    else:
        pipeline = transformers.pipeline(
            "text-generation",
            model=model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        # pipeline = None
    
    print("Loaded model")
    return pipeline, model_name

