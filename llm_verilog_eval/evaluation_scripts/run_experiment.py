# llm_verilog_eval/evaluation_scripts/run_experiment.py
import os
import sys
import subprocess
from datetime import datetime

# Add utils directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))
try:
    from llm_interface import load_model_and_tokenizer, generate_verilog
except ImportError as e:
    print(f"Error: Could not import from llm_interface.py: {e}")
    print("Ensure it's in the ../utils/ directory and an __init__.py file exists in utils if needed.")
    sys.exit(1)

# --- Configuration ---
# For a very quick pipeline test, use a small, fast model if Qwen is too slow.
# However, smaller models are unlikely to generate correct Verilog.
# MODEL_NAME_OR_PATH = "Salesforce/codegen-350M-mono" # Example smaller model
MODEL_NAME_OR_PATH = "/data/genai/models/Qwen2.5-Coder-32B-Instruct" #"Qwen/Qwen2.5-Coder-32B-Instruct" # Your target model
# MODEL_NAME_OR_PATH = "/data/genai/models/Qwen3-0.6B"
MODEL_NAME_OR_PATH = "/data/genai/models/gemma-3-27b-it"
QUANTIZATION = None # Or "8bit", "4bit" for larger models if VRAM is an issue

PROJECT_ROOT = "/data/genai/kmcho/llm_generation_test/verilog-i2c" #"/data/genai/kmcho/verilog-i2c" # Your project root

# === Simple Test Case Configuration ===
MODULE_NAME = "simple_and"
TESTBENCH_SCRIPT_NAME = "test_simple_and.py"    # To be passed to evaluate_rtl.sh
DUT_ENV_VAR_NAME = "DUT_RTL_FILE_SIMPLE_AND" # To be passed to evaluate_rtl.sh and used by test_simple_and.py

MODULE_NAME = "i2c_init"
TESTBENCH_SCRIPT_NAME = "test_i2c_init.py"    # To be passed to evaluate_rtl.sh
DUT_ENV_VAR_NAME = "DUT_RTL_FILE_I2C_INIT" # To be passed to evaluate_rtl.sh and used by test_simple_and.py
# ====================================

EXPERIMENT_MODE = "full_completion"
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
    
    prompts_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "prompts", MODULE_NAME)
    generated_rtl_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "generated_rtl", MODULE_NAME)
    results_module_dir = os.path.join(PROJECT_ROOT, "llm_verilog_eval", "results", MODULE_NAME)

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
        user_instruction = (
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
        full_prompt_content = f"{prompt_header_and_comment}"

        messages = [
            {"role": "system", "content": user_instruction},
            # Pass the Verilog header and initial comments as the start of the user's request for completion
            {"role": "user", "content": f"Complete this Verilog module:\n```verilog\n{full_prompt_content}\n```"}
        ]
        try:
            prompt_text_for_llm = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True # Important!
            )
            print(f"DEBUG: Applied chat template. Resulting prompt starts with: {prompt_text_for_llm[:200]}")
        except Exception as e:
            print(f"Error applying chat template: {e}. Using raw header as fallback.")
            prompt_text_for_llm = full_prompt_content # Fallback
        # --- END CRITICAL SECTION ---
    elif EXPERIMENT_MODE == "partial_completion":
        print("Partial completion mode setup not fully implemented in this script yet.")
        # Here you would load the reference RTL, call a masking function from masking_utils.py,
        # and then construct a prompt asking the LLM to fill in the masked parts.
        sys.exit(1)
    else: # Placeholder for other modes
        print(f"Error: Experiment mode '{EXPERIMENT_MODE}' not fully set up for this script.")
        sys.exit(1)

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