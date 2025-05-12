# llm_verilog_eval/evaluation_scripts/run_experiment.py
import os
import sys
import subprocess
from datetime import datetime

# Add utils directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
try:
    from llm_interface import load_model_and_tokenizer, generate_verilog
except ImportError:
    print("Error: Could not import from llm_interface.py.")
    print("Ensure it's in the ../utils/ directory and an __init__.py file exists in utils if needed.")
    sys.exit(1)

# --- Configuration ---
MODEL_NAME_OR_PATH = "/data/genai/models/Qwen2.5-Coder-32B-Instruct" #"Qwen/Qwen2.5-Coder-32B-Instruct" # Or your specific local path/name
# MODEL_NAME_OR_PATH = "Salesforce/codegen-350M-mono" # Smaller model 
QUANTIZATION = None # None, "8bit", or "4bit" (Ensure bitsandbytes is installed for 8bit/4bit)

PROJECT_ROOT = "/data/genai/kmcho/llm_generation_test/verilog-i2c" #"/data/genai/kmcho/verilog-i2c" # Your project root
MODULE_NAME = "i2c_init"
EXPERIMENT_MODE = "full_completion" # Later: "partial_completion"
# --- End Configuration ---

def cleanup_generated_verilog(raw_output):
    """
    Attempts to extract the Verilog code block from the LLM's raw output.
    LLMs often wrap code in ```verilog ... ``` or might add explanations.
    """
    # Common markdown code block
    if "```verilog" in raw_output.lower():
        code = raw_output.split("```verilog")[1 if "```verilog" in raw_output else 0]
        code = code.split("```")[0]
        return code.strip()
    elif "```" in raw_output: # Generic code block
        if raw_output.strip().startswith("```") and raw_output.strip().endswith("```"):
             code = raw_output.strip()[3:-3].strip()
             # Check if the first line after ``` is verilog (case insensitive)
             if code.lower().startswith("verilog\n"):
                 code = code.split("\n",1)[1]
             return code
        # Fallback if it's just one block
        code = raw_output.split("```")[1 if "```" in raw_output else 0]
        return code.strip()

    # If no markdown, try to find module ... endmodule
    # This is a very basic heuristic and might need improvement
    module_start_idx = raw_output.lower().find("module ")
    module_end_idx = raw_output.lower().rfind("endmodule")

    if module_start_idx != -1 and module_end_idx != -1 and module_start_idx < module_end_idx:
        return raw_output[module_start_idx : module_end_idx + len("endmodule")].strip()
    
    print("Warning: Could not reliably extract Verilog block using ```verilog or module...endmodule. Returning raw output.")
    return raw_output.strip()


def main():
    print(f"Starting experiment for module: {MODULE_NAME}, mode: {EXPERIMENT_MODE}")
    
    # --- 1. Load LLM (this can take time) ---
    try:
        model, tokenizer = load_model_and_tokenizer(MODEL_NAME_OR_PATH, use_quantization=QUANTIZATION)
    except Exception as e:
        print(f"FATAL: Failed to load model or tokenizer: {e}")
        print("Please check model name, path, internet connection (for download), and hardware resources (VRAM).")
        if QUANTIZATION:
            print(f"Ensure 'bitsandbytes' is installed correctly if using {QUANTIZATION} quantization.")
        sys.exit(1)

    # --- 2. Prepare Prompt and Output Paths ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Construct full paths
    prompts_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "prompts", MODULE_NAME)
    generated_rtl_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "generated_rtl", MODULE_NAME)
    results_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "results", MODULE_NAME)

    os.makedirs(generated_rtl_module_dir, exist_ok=True)
    os.makedirs(results_module_dir, exist_ok=True)

    # Sanitize model name for filename
    safe_model_name = MODEL_NAME_OR_PATH.replace('/', '_').replace('-', '_')
    
    output_v_filename = f"{MODULE_NAME}_{safe_model_name}_{EXPERIMENT_MODE}_{timestamp}.v"
    output_v_filepath = os.path.join(generated_rtl_module_dir, output_v_filename)
    
    log_filename = f"{MODULE_NAME}_{safe_model_name}_{EXPERIMENT_MODE}_{timestamp}_eval.log"
    log_filepath = os.path.join(results_module_dir, log_filename) # Will be made absolute by evaluate_rtl.sh

    prompt_text_for_llm = ""

    if EXPERIMENT_MODE == "full_completion":
        header_file_path = os.path.join(prompts_module_dir, "full_completion_header.v")
        if not os.path.exists(header_file_path):
            print(f"Error: Prompt header file not found at {header_file_path}")
            sys.exit(1)
        with open(header_file_path, 'r') as f:
            prompt_header = f.read()
        
        # This is where you construct the actual prompt text that will be sent to the LLM.
        # For Qwen-Instruct, you need to use its chat template.
        # The content of `full_completion_header.v` is the Verilog code prefix/context.
        # The instruction tells the LLM what to do with it.
        # Example for Qwen Instruct (YOU MUST VERIFY AND USE THE CORRECT TEMPLATE):
        user_instruction = (
            "Complete the following Verilog module. "
            "Ensure the logic correctly implements an I2C initializer based on the comments and port names. "
            "The module uses an internal `init_data` ROM and a state machine to control AXI-Stream command and data outputs. "
            "The `busy` signal should be managed appropriately. Adhere to standard Verilog 2001 syntax."
        )
        messages = [
            {"role": "system", "content": "You are an expert Verilog HDL code generation assistant. Provide only the completed Verilog code."},
            {"role": "user", "content": f"{user_instruction}\n\n```verilog\n{prompt_header}\n```"} # Pass the header as part of the user message
        ]
        try:
            prompt_text_for_llm = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True # Crucial for instruct models
            )
        except Exception as e:
            print(f"Error applying chat template: {e}. Ensure your tokenizer is for an instruct/chat model.")
            print("Falling back to using raw header as prompt - THIS MAY PRODUCE POOR RESULTS for instruct models.")
            prompt_text_for_llm = prompt_header # Fallback, likely suboptimal

    elif EXPERIMENT_MODE == "partial_completion":
        print("Partial completion mode setup not fully implemented in this script yet.")
        # Here you would load the reference RTL, call a masking function from masking_utils.py,
        # and then construct a prompt asking the LLM to fill in the masked parts.
        sys.exit(1)
    else:
        print(f"Error: Unknown experiment mode '{EXPERIMENT_MODE}'")
        sys.exit(1)

    # --- 3. Call LLM to Generate Verilog ---
    print(f"Generating Verilog using {MODEL_NAME_OR_PATH}...")
    raw_llm_output = generate_verilog(model, tokenizer, prompt_text_for_llm)
    
    print("\n--- Raw LLM Output (first 500 chars) ---")
    print(raw_llm_output[:500])
    print("--------------------------------------\n")

    generated_verilog_code = cleanup_generated_verilog(raw_llm_output)

    with open(output_v_filepath, 'w') as f:
        f.write(generated_verilog_code)
    print(f"Cleaned and saved generated RTL to: {output_v_filepath}")

    # --- 4. Trigger Evaluation ---
    print(f"Starting evaluation for {output_v_filepath}...")
    eval_script_path = os.path.join(os.path.dirname(__file__), "evaluate_rtl.sh")
    
    # Make sure evaluate_rtl.sh is executable (should be done once, but good practice)
    try:
        subprocess.run(['chmod', '+x', eval_script_path], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not chmod +x {eval_script_path}: {e.stderr.decode()}")

    # Pass absolute path for generated RTL and log file to the shell script
    abs_output_v_filepath = os.path.abspath(output_v_filepath)
    abs_log_filepath = os.path.abspath(log_filepath)

    print(f"Calling: {eval_script_path} {abs_output_v_filepath} {abs_log_filepath}")
    eval_process = subprocess.run(
        [eval_script_path, abs_output_v_filepath, abs_log_filepath],
        capture_output=True, text=True
    )

    print("\n--- Evaluation Script STDOUT ---")
    print(eval_process.stdout)
    print("--- Evaluation Script STDERR ---")
    print(eval_process.stderr) # Important for debugging issues in evaluate_rtl.sh
    print("------------------------------\n")

    if eval_process.returncode == 0:
        print(f"SUCCESS: Evaluation PASSED for {output_v_filename}")
    else:
        print(f"FAILURE: Evaluation FAILED for {output_v_filename}")
        print(f"         MyHDL/Icarus logs should be in: {abs_log_filepath}")

if __name__ == "__main__":
    main()