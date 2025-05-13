# llm_verilog_eval/utils/llm_interface.py
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Global cache to avoid reloading models and tokenizers unnecessarily
_model_cache = {}
_tokenizer_cache = {}

def load_model_and_tokenizer(model_name_or_path, use_quantization=None):
    if model_name_or_path in _model_cache:
        return _model_cache[model_name_or_path], _tokenizer_cache[model_name_or_path]

    print(f"Loading tokenizer for {model_name_or_path}...")
    # Qwen models often require trust_remote_code=True
    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, trust_remote_code=True)

    print(f"Loading model {model_name_or_path}...")
    quant_config = {}
    if use_quantization == "8bit":
        quant_config['load_in_8bit'] = True
        print("Applying 8-bit quantization.")
    elif use_quantization == "4bit":
        quant_config['load_in_4bit'] = True
        print("Applying 4-bit quantization.")

    model = AutoModelForCausalLM.from_pretrained(
        model_name_or_path,
        device_map="auto",  # Uses accelerate to distribute model across GPUs/CPU if needed
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16, # Or "auto"
        trust_remote_code=True,
        **quant_config
    )
    
    # Handle cases where tokenizer might not have a pad_token_id set
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is not None:
            print("Tokenizer `pad_token_id` not set. Using `eos_token_id` as `pad_token_id`.")
            tokenizer.pad_token_id = tokenizer.eos_token_id
        else:
            # Add a new pad token if neither eos_token nor pad_token is set. This is less common.
            print("Adding new pad token to tokenizer.")
            tokenizer.add_special_tokens({'pad_token': '[PAD]'})
            model.resize_token_embeddings(len(tokenizer))


    print(f"Model {model_name_or_path} loaded on device(s): {model.hf_device_map if hasattr(model, 'hf_device_map') else model.device}")

    _model_cache[model_name_or_path] = model
    _tokenizer_cache[model_name_or_path] = tokenizer
    return model, tokenizer

def generate_verilog(model, tokenizer, prompt_text, max_new_tokens=8192, temperature=0.7):
    """
    Generates Verilog code using the provided model, tokenizer, and prompt.

    IMPORTANT: The prompt_text formatting is CRITICAL for instruct-tuned models
    like Qwen-Coder-Instruct. You MUST consult the model's documentation/card
    on Hugging Face for the correct chat/instruction template.
    """

    # --- THIS IS A CRITICAL SECTION ---
    # The input to the model needs to be formatted according to its specific requirements.
    # For Qwen-Instruct models, this usually involves a chat template.
    # Example (you MUST verify and adapt this for Qwen2.5-Coder-32B-Instruct):
    # messages = [
    #     {"role": "system", "content": "You are an expert Verilog HDL code generation assistant."},
    #     {"role": "user", "content": f"Generate the Verilog code for the following task:\n{prompt_text}"}
    # ]
    # For some code completion models, you might directly feed the `prompt_text` if it's a code prefix.
    # For Qwen2 Instruct series, it's likely a chat template:
    # input_text_for_model = tokenizer.apply_chat_template(
    #     messages,
    #     tokenize=False,
    #     add_generation_prompt=True # Important for instructing the model to generate
    # )
    # For now, let's assume prompt_text IS the fully formatted input the model expects:
    #input_text_for_model = prompt_text # <<< REPLACE THIS WITH CORRECT QWEN TEMPLATING

    # Qwen2.5 formatting start
    prompt = "You are an expert Verilog HDL code generation assistant."
    messages = [
        {"role": "system", "content": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."},
        {"role": "user", "content": prompt}
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    # Qwen2.5 formatting end
    # Currently formatting seems to be done correctly at the run_experiment.py stage
    input_text_for_model = prompt_text

    print("\n--- Input to LLM (first 500 chars) ---")
    print(input_text_for_model[:500])
    print("-------------------------------------\n")
    
    model_inputs = tokenizer([input_text_for_model], return_tensors="pt", padding=True).to(model.device if hasattr(model, 'device') else "cuda")


    generated_ids = model.generate(
        model_inputs.input_ids,
        attention_mask=model_inputs.attention_mask, # Include attention mask if padding
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=0.95, # Common value for top_p
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        do_sample=True if temperature > 0 else False # do_sample must be true for temperature to have effect
    )

    # Decode only the newly generated tokens (excluding the prompt)
    input_token_len = model_inputs.input_ids.shape[1]
    output_tokens = generated_ids[0][input_token_len:]
    
    decoded_output = tokenizer.decode(output_tokens, skip_special_tokens=True)
    
    return decoded_output