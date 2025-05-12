# llm_verilog_eval/evaluation_scripts/run_experiment.py
import os
import sys
import subprocess
from datetime import datetime

# Add utils directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
try:
    from llm_interface import load_model_and_tokenizer, generate_verilog
    from masking_utils import mask_verilog_lines, DEFAULT_MASK_TOKEN
except ImportError as e:
    print(f"Error: Could not import from llm_interface.py: {e}")
    print("Ensure it's in the ../utils/ directory and an __init__.py file exists in utils if needed.")
    sys.exit(1)

# --- Configuration ---
# For a very quick pipeline test, use a small, fast model if Qwen is too slow.
# However, smaller models are unlikely to generate correct Verilog.
# MODEL_NAME_OR_PATH = "Salesforce/codegen-350M-mono" # Example smaller model
MODEL_NAME_OR_PATH = "/data/genai/models/Qwen2.5-Coder-32B-Instruct" #"Qwen/Qwen2.5-Coder-32B-Instruct" # Your target model
MODEL_NAME_OR_PATH = "/data/genai/models/Qwen3-0.6B"
#MODEL_NAME_OR_PATH = "/data/genai/models/gemma-3-27b-it"
MODEL_NAME_OR_PATH = "/data/genai/models/Qwen2.5-Coder-7B"
QUANTIZATION = None # Or "8bit", "4bit" for larger models if VRAM is an issue

PROJECT_ROOT = "/data/genai/kmcho/llm_generation_test/verilog-i2c" #"/data/genai/kmcho/verilog-i2c" # Your project root

# === Simple Test Case Configuration ===
MODULE_NAME = "simple_and"
TESTBENCH_SCRIPT_NAME = "test_simple_and.py"    # To be passed to evaluate_rtl.sh
DUT_ENV_VAR_NAME = "DUT_RTL_FILE_SIMPLE_AND" # To be passed to evaluate_rtl.sh and used by test_simple_and.py

# MODULE_NAME = "i2c_init"
# TESTBENCH_SCRIPT_NAME = "test_i2c_init.py"    # To be passed to evaluate_rtl.sh
# DUT_ENV_VAR_NAME = "DUT_RTL_FILE_I2C_INIT" # To be passed to evaluate_rtl.sh and used by test_simple_and.py

# Module-specific settings (these will be used based on MODULE_NAME)
MODULE_CONFIGS = {
    "simple_and": {
        "testbench_script": "test_simple_and.py",
        "dut_env_var": "DUT_RTL_FILE_SIMPLE_AND",
        "reference_rtl_filename": "simple_and.v", # For partial completion
        "num_lines_to_mask": 10, # Mask the single 'assign' line
    },
    "i2c_init": {
        "testbench_script": "test_i2c_init.py",
        # Ensure your test_i2c_init.py uses this exact env var name if you changed it
        "dut_env_var": "DUT_RTL_FILE_I2C_INIT", 
        "reference_rtl_filename": "i2c_init.v", # Assumes this exists in PROJECT_ROOT/rtl/
        "num_lines_to_mask": 5, # Example, adjust as needed
    }
}

if MODULE_NAME not in MODULE_CONFIGS:
    print(f"Error: Module '{MODULE_NAME}' is not defined in MODULE_CONFIGS.")
    sys.exit(1)

CURRENT_MODULE_CONFIG = MODULE_CONFIGS[MODULE_NAME]
TESTBENCH_SCRIPT_NAME = CURRENT_MODULE_CONFIG["testbench_script"]
DUT_ENV_VAR_NAME = CURRENT_MODULE_CONFIG["dut_env_var"]
REFERENCE_RTL_FILENAME = CURRENT_MODULE_CONFIG.get("reference_rtl_filename") # Might not exist for all modules if only doing full_completion
NUM_LINES_TO_MASK = CURRENT_MODULE_CONFIG.get("num_lines_to_mask", 0)


# ====================================

EXPERIMENT_MODE = "full_completion"
EXPERIMENT_MODE = "partial_completion"
# --- End Configuration ---

def cleanup_generated_verilog(raw_output):
    # (Use the same cleanup_generated_verilog function as provided in the previous response)
    # Common markdown code block
    if "```verilog" in raw_output.lower():
        parts = raw_output.split("```verilog", 1)
        if len(parts) > 1:
            code = parts[1].split("```")[0]
            return code.strip()
    elif "```" in raw_output: # Generic code block
        parts = raw_output.split("```", 1)
        if len(parts) > 1:
            code_block_content = parts[1].split("```")[0]
            # Remove potential language specifier like "verilog" if it's the first line
            lines = code_block_content.strip().splitlines()
            if lines and lines[0].strip().lower() == "verilog":
                return "\n".join(lines[1:]).strip()
            return code_block_content.strip()

    module_start_idx = raw_output.lower().find("module ")
    module_end_idx = raw_output.lower().rfind("endmodule")
    if module_start_idx != -1 and module_end_idx != -1 and module_start_idx < module_end_idx:
        return raw_output[module_start_idx : module_end_idx + len("endmodule")].strip()
    
    print("Warning: Could not reliably extract Verilog block. Returning raw output minus common LLM chatter.")
    # Basic removal of common preamble/postamble if no clear block found
    lines = raw_output.splitlines()
    filtered_lines = [line for line in lines if not (line.lower().startswith("here is the verilog") or line.lower().startswith("certainly, here is"))]
    return "\n".join(filtered_lines).strip()


def main():
    print(f"Starting experiment for module: {MODULE_NAME}, mode: {EXPERIMENT_MODE}")
    
    try:
        model, tokenizer = load_model_and_tokenizer(MODEL_NAME_OR_PATH, use_quantization=QUANTIZATION)
    except Exception as e:
        print(f"FATAL: Failed to load model or tokenizer: {e}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    seed_for_masking = 42 # Use a fixed seed for reproducibility
    
    prompts_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "prompts", MODULE_NAME)
    generated_rtl_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "generated_rtl", MODULE_NAME)
    results_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "results", MODULE_NAME)
    reference_rtl_dir = os.path.join(PROJECT_ROOT, "rtl") # For partial completion source


    os.makedirs(prompts_module_dir, exist_ok=True)
    os.makedirs(generated_rtl_module_dir, exist_ok=True)
    os.makedirs(results_module_dir, exist_ok=True)

    safe_model_name = MODEL_NAME_OR_PATH.replace('/', '_').replace('-', '_')
    output_v_filename = f"{MODULE_NAME}_{safe_model_name}_{EXPERIMENT_MODE}_{timestamp}.v"
    output_v_filepath = os.path.join(generated_rtl_module_dir, output_v_filename)
    log_filename = f"{MODULE_NAME}_{safe_model_name}_{EXPERIMENT_MODE}_{timestamp}_eval.log"
    log_filepath = os.path.join(results_module_dir, log_filename)

    prompt_text_for_llm = ""
    if EXPERIMENT_MODE == "full_completion":
        header_file_path = os.path.join(prompts_module_dir, "full_completion_header.v")
        if not os.path.exists(header_file_path):
            print(f"Error: Prompt header file not found at {header_file_path}")
            sys.exit(1)
        with open(header_file_path, 'r') as f:
            prompt_header_and_comment = f.read()
        
        # --- CRITICAL: Adapt this prompt format to your specific Qwen model! ---
        # This is a general example. Consult the Qwen model card on Hugging Face.
        system_instruction = (
            "You are an expert Verilog HDL code generation assistant. "
            "Your task is to complete the given Verilog module based on the comments and port definitions. "
            "Provide only the completed Verilog code that fits within the module structure. "
            "Do not add any explanatory text before or after the Verilog code block itself."
            "Complete the full verilog module including the header portion so that the entire module and endmodule is included."
            "Use Verilog-2001 syntax, do not use SystemVerilog or other variants."
        )
        # The `prompt_header_and_comment` contains the `module ... endmodule` skeleton with a comment.
        # The LLM should fill in the logic.
        # Construct the input for the LLM:
        user_prompt_content = f"Complete this Verilog module:\n```verilog\n{prompt_header_and_comment}\n```"
        # --- END CRITICAL SECTION ---
    elif EXPERIMENT_MODE == "partial_completion":
        if not REFERENCE_RTL_FILENAME:
            print(f"Error: 'reference_rtl_filename' not configured for module '{MODULE_NAME}' in partial_completion mode.")
            sys.exit(1)
        
        reference_rtl_path = os.path.join(reference_rtl_dir, REFERENCE_RTL_FILENAME)
        if not os.path.exists(reference_rtl_path):
            print(f"Error: Reference RTL file '{REFERENCE_RTL_FILENAME}' not found at {reference_rtl_path} for partial completion.")
            sys.exit(1)
        
        masked_rtl_filename = f"{MODULE_NAME}_masked_for_{timestamp}.v"
        # Store masked files in the module's prompt directory for inspection
        masked_rtl_filepath = os.path.join(prompts_module_dir, masked_rtl_filename)

        print(f"Masking {NUM_LINES_TO_MASK} line(s) in {reference_rtl_path} (seed: {seed_for_masking})...")
        if not mask_verilog_lines(
            reference_rtl_path, 
            masked_rtl_filepath, 
            num_lines_to_mask=NUM_LINES_TO_MASK, 
            mask_token=DEFAULT_MASK_TOKEN, 
            seed=seed_for_masking,
            module_name_for_ref=MODULE_NAME
        ):
            print(f"Error: Failed to create masked Verilog file at {masked_rtl_filepath}")
            sys.exit(1)

        with open(masked_rtl_filepath, 'r') as f:
            masked_code_content = f.read()
        
        print(f"--- Masked Verilog Content (from {masked_rtl_filepath}) Used for Prompt ---")
        print(masked_code_content)
        print("-------------------------------------------------------------------------")

        system_instruction = (
            "You are an expert Verilog HDL code generation assistant. "
            f"The following Verilog code contains one or more masked lines indicated by '{DEFAULT_MASK_TOKEN}'. "
            "Your task is to fill in these masked lines with the correct Verilog code to make the module complete and functional. "
            "Provide the entire completed Verilog module, with the masked sections filled appropriately. "
            "Do not add any other explanatory text."
            "Use Verilog-2001 syntax, do not use SystemVerilog or other variants."
        )
        user_prompt_content = f"Complete the Verilog code by filling in the masked lines:\n```verilog\n{masked_code_content}\n```"
    else: # Placeholder for other modes
        print(f"Error: Experiment mode '{EXPERIMENT_MODE}' not fully set up for this script.")
        sys.exit(1)

    # Common prompt assembly using chat template
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt_content}
    ]
    try:
        prompt_text_for_llm = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True # Crucial for instruct models
        )
        print(f"DEBUG: Applied chat template. Resulting prompt starts with: {prompt_text_for_llm[:300]}...")
    except Exception as e:
        print(f"Error applying chat template: {e}. Using concatenated string as fallback (may yield poor results).")
        prompt_text_for_llm = system_instruction + "\n\n" + user_prompt_content # Basic fallback


    print(f"Generating Verilog using {MODEL_NAME_OR_PATH}...")
    raw_llm_output = generate_verilog(model, tokenizer, prompt_text_for_llm)
    
    print(f"\n--- Raw LLM Output (first 1000 chars) ---\n{raw_llm_output[:1000]}\n--------------------------------------\n")

    generated_verilog_code = cleanup_generated_verilog(raw_llm_output)

    # Ensure the generated code at least starts with "module" if it's not empty
    if generated_verilog_code and not generated_verilog_code.strip().lower().startswith("module"):
        # If the header was `module foo (...); //LLM fill here \n endmodule`
        # And LLM just gives `assign y = a & b;`
        # We need to insert it into the header.
        # For simplicity, let's assume the LLM tries to give the full module if cleanup was basic.
        # More robust: if LLM output is just the body, insert it into the header.
        # For now, we rely on the LLM providing the full module structure if the prompt is a completion task.
        # Or, the prompt header itself is structured like: module ... // LLM completes from here ... endmodule
        # And `generate_verilog` is expected to return only the completion part.
        # Let's adjust the prompt slightly for simple_and and assume LLM completes it.
        # The `full_completion_header.v` for `simple_and` asks LLM to implement logic.
        # If LLM only provides `assign y = a & b;`, the cleanup needs to be smart or the prompt needs to guide it
        # to repeat the module header.
        # For the current `simple_and` header, the LLM is expected to provide the logic *within* the given `module ... endmodule` block.
        # The `generate_verilog` function in `llm_interface.py` returns only *newly* generated tokens.
        # So, if the prompt was `module simple_and (...); // complete here`, the LLM output would be `assign y = a & b; endmodule`.
        # Let's assume for now the `cleanup_generated_verilog` handles extracting the full module.
        # If the LLM only generates the *inside* of the module, the `full_completion_header.v` should be used
        # as a template to insert the LLM's generated logic.
        # For now, the `cleanup_generated_verilog` tries to find a complete `module...endmodule` block.
        pass


    with open(output_v_filepath, 'w') as f:
        f.write(generated_verilog_code)
    print(f"Cleaned and saved generated RTL to: {output_v_filepath}")

    print(f"Starting evaluation for {output_v_filepath}...")
    eval_script_path = os.path.join(os.path.dirname(__file__), "evaluate_rtl.sh")
    
    try: subprocess.run(['chmod', '+x', eval_script_path], check=True, capture_output=True)
    except subprocess.CalledProcessError as e: print(f"Warning: Could not chmod +x {eval_script_path}: {e.stderr.decode()}")

    abs_output_v_filepath = os.path.abspath(output_v_filepath)
    abs_log_filepath = os.path.abspath(log_filepath)

    print(f"Calling: {eval_script_path} {abs_output_v_filepath} {TESTBENCH_SCRIPT_NAME} {DUT_ENV_VAR_NAME} {abs_log_filepath}")
    eval_process = subprocess.run(
        [eval_script_path, abs_output_v_filepath, TESTBENCH_SCRIPT_NAME, DUT_ENV_VAR_NAME, abs_log_filepath],
        capture_output=True, text=True
    )

    print("\n--- Evaluation Script STDOUT ---")
    print(eval_process.stdout)
    print("\n--- Evaluation Script STDERR ---") # This will show iverilog/vvp errors if any
    print(eval_process.stderr)
    print("------------------------------\n")

    if eval_process.returncode == 0:
        print(f"SUCCESS: Evaluation PASSED for {output_v_filename}")
    else:
        print(f"FAILURE: Evaluation FAILED for {output_v_filename}")
        print(f"         MyHDL/Icarus logs should be in: {abs_log_filepath}")

if __name__ == "__main__":
    main()