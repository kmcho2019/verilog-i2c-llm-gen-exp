# llm_verilog_eval/utils/masking_utils.py
import random
import os

DEFAULT_MASK_TOKEN = "// [LLM_FILL_HERE]"

def mask_verilog_lines(
    input_rtl_path: str,
    output_masked_rtl_path: str,
    num_lines_to_mask: int = 1,
    mask_token: str = DEFAULT_MASK_TOKEN,
    seed: int = None,
    module_name_for_ref: str = "unknown_module" # For more specific logging
):
    """
    Reads a Verilog file, randomly selects a specified number of suitable lines
    to mask, and writes the masked version to a new file.

    Args:
        input_rtl_path: Path to the input Verilog file.
        output_masked_rtl_path: Path where the masked Verilog will be saved.
        num_lines_to_mask: The number of lines to mask.
        mask_token: The string to replace the selected lines with.
        seed: Optional random seed for reproducibility.
        module_name_for_ref: Name of the module for logging purposes.
    """
    if seed is not None:
        random.seed(seed)

    try:
        with open(input_rtl_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error [mask_verilog_lines]: Input RTL file for '{module_name_for_ref}' not found at {input_rtl_path}")
        return False

    candidate_indices = []
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        # Exclude empty lines, pure comment lines, module/endmodule, `timescale, `define, parameters, initial blocks for $tasks
        if not stripped_line:
            continue
        if stripped_line.startswith("//") and not any(c.isalnum() for c in stripped_line[2:]): # Avoid masking comments with code
            continue
        if stripped_line.startswith("/*") and stripped_line.endswith("*/") and stripped_line.count("/*") == 1 and stripped_line.count("*/") == 1: # Simple block comment
             continue
        low_stripped_line = stripped_line.lower()
        if low_stripped_line.startswith("module ") or \
           low_stripped_line.startswith("endmodule") or \
           low_stripped_line.startswith("`timescale") or \
           low_stripped_line.startswith("`define") or \
           low_stripped_line.startswith("parameter ") or \
           low_stripped_line.startswith("localparam ") or \
           low_stripped_line.startswith("input ") or \
           low_stripped_line.startswith("output ") or \
           low_stripped_line.startswith("inout ") or \
           low_stripped_line.startswith("initial"): # Basic initial block check, might need refinement
            continue
        candidate_indices.append(i)

    if not candidate_indices:
        print(f"Warning [mask_verilog_lines]: No candidate lines found for masking in '{module_name_for_ref}' from {input_rtl_path}")
        with open(output_masked_rtl_path, 'w') as f: # Write original if no candidates
            f.writelines(lines)
        return True # Or False if this is an error condition for you

    actual_num_to_mask = min(num_lines_to_mask, len(candidate_indices))
    if num_lines_to_mask > len(candidate_indices):
        print(f"Warning [mask_verilog_lines]: Requested to mask {num_lines_to_mask} lines for '{module_name_for_ref}', "
              f"but only {len(candidate_indices)} candidate lines available. Masking {actual_num_to_mask} lines.")
    
    lines_to_mask_indices = sorted(random.sample(candidate_indices, actual_num_to_mask))

    masked_lines_content = list(lines)
    print(f"INFO [mask_verilog_lines]: For module '{module_name_for_ref}', masking lines at original indices (1-based):")
    for index in lines_to_mask_indices:
        original_line_content = masked_lines_content[index].strip()
        leading_whitespace = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
        masked_lines_content[index] = leading_whitespace + mask_token + "\n"
        print(f"  Line {index + 1}: '{original_line_content}'  =>  '{mask_token}'")

    try:
        os.makedirs(os.path.dirname(output_masked_rtl_path), exist_ok=True)
        with open(output_masked_rtl_path, 'w') as f:
            f.writelines(masked_lines_content)
        print(f"INFO [mask_verilog_lines]: Masked RTL for '{module_name_for_ref}' saved to: {output_masked_rtl_path}")
        return True
    except IOError as e:
        print(f"Error [mask_verilog_lines]: Could not write masked RTL for '{module_name_for_ref}' to {output_masked_rtl_path}: {e}")
        return False

if __name__ == '__main__':
    # Create a dummy utils directory if this script is run directly for testing
    if not os.path.exists("../utils"): # Assuming this script is in utils itself
        os.makedirs("../utils", exist_ok=True)

    # Example Usage for testing masking_utils.py directly
    dummy_input_path = "dummy_mask_input.v"
    dummy_output_path = "dummy_mask_output_masked.v" # Will be created in the current dir
    
    dummy_rtl_content = """module test_adder (
    input wire [3:0] a,
    input wire [3:0] b,
    output wire [4:0] sum
);
    // This is a simple adder
    // It should perform addition
    parameter WIDTH = 4;
    localparam EXTRA_BIT = 1;

    assign sum = a + b; // Line to be masked
    
    // Another operation
    wire [WIDTH-1:0] diff;
    assign diff = a - b; // Another candidate for masking
endmodule
"""
    with open(dummy_input_path, "w") as f:
        f.write(dummy_rtl_content)

    print(f"Testing mask_verilog_lines with {dummy_input_path}...")
    success = mask_verilog_lines(
        dummy_input_path, 
        dummy_output_path, 
        num_lines_to_mask=1, 
        seed=42,
        module_name_for_ref="test_adder_dummy"
    )
    if success:
        print(f"Masking successful. Check {dummy_output_path}")
        with open(dummy_output_path, 'r') as f:
            print("\nMasked content:")
            print(f.read())
    else:
        print("Masking failed.")
    
    # Clean up dummy files
    if os.path.exists(dummy_input_path): os.remove(dummy_input_path)
    if os.path.exists(dummy_output_path): os.remove(dummy_output_path)