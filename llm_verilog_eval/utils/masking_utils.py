# llm_verilog_eval/utils/masking_utils.py
import random
import os # Added for os.path.dirname, os.makedirs

DEFAULT_MASK_TOKEN = "// [LLM_FILL_HERE]"

def mask_verilog_lines(
    input_rtl_path: str,
    output_masked_rtl_path: str,
    num_lines_to_mask: int = 1,
    mask_token: str = DEFAULT_MASK_TOKEN,
    seed: int = None,
    module_name_for_ref: str = "unknown_module", # For logging
    # New parameters for range specification (1-based line numbers)
    mask_after_line: int = None,
    mask_start_line: int = None,
    mask_end_line: int = None
):
    """
    Reads a Verilog file, selects suitable lines within a specified range
    (or the whole file if no range is given) to mask, and writes the masked
    version to a new file.

    Args:
        input_rtl_path: Path to the input Verilog file.
        output_masked_rtl_path: Path where the masked Verilog will be saved.
        num_lines_to_mask: The number of lines to mask within the specified range.
        mask_token: The string to replace the selected lines with.
        seed: Optional random seed for reproducibility.
        module_name_for_ref: Name of the module for logging purposes.
        mask_after_line: (1-based) Start masking only *after* this line number.
        mask_start_line: (1-based) Start masking *at* this line number (inclusive).
        mask_end_line: (1-based) Stop masking *at* this line number (inclusive).
                       Requires mask_start_line to be set.
    """
    if seed is not None:
        random.seed(seed)

    # Validate line number inputs
    if mask_after_line is not None and (mask_start_line is not None or mask_end_line is not None):
        print(f"Warning [mask_verilog_lines]: Both 'mask_after_line' and 'mask_start/end_line' specified for '{module_name_for_ref}'. "
              "Prioritizing 'mask_after_line'.")
        mask_start_line = None
        mask_end_line = None
    if mask_start_line is not None and mask_end_line is None:
        print(f"Warning [mask_verilog_lines]: 'mask_start_line' specified for '{module_name_for_ref}' but 'mask_end_line' is missing. "
              "Ignoring range.")
        mask_start_line = None
    if mask_start_line is not None and mask_end_line is not None and mask_start_line > mask_end_line:
        print(f"Error [mask_verilog_lines]: 'mask_start_line' ({mask_start_line}) cannot be greater than 'mask_end_line' ({mask_end_line}) for '{module_name_for_ref}'.")
        return False
    if mask_after_line is not None and mask_after_line < 0:
         print(f"Error [mask_verilog_lines]: 'mask_after_line' ({mask_after_line}) cannot be negative for '{module_name_for_ref}'.")
         return False
    if mask_start_line is not None and mask_start_line <= 0:
         print(f"Error [mask_verilog_lines]: 'mask_start_line' ({mask_start_line}) must be positive for '{module_name_for_ref}'.")
         return False
    if mask_end_line is not None and mask_end_line <= 0:
         print(f"Error [mask_verilog_lines]: 'mask_end_line' ({mask_end_line}) must be positive for '{module_name_for_ref}'.")
         return False


    try:
        with open(input_rtl_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error [mask_verilog_lines]: Input RTL file for '{module_name_for_ref}' not found at {input_rtl_path}")
        return False
    
    total_lines = len(lines)

    # Determine the search range for candidate lines based on parameters
    # Convert 1-based line numbers from args to 0-based indices
    range_start_idx = 0
    range_end_idx = total_lines # Exclusive end index

    if mask_after_line is not None:
        if mask_after_line >= total_lines:
             print(f"Warning [mask_verilog_lines]: 'mask_after_line' ({mask_after_line}) is beyond the last line ({total_lines}) for '{module_name_for_ref}'. No lines to mask.")
             range_start_idx = total_lines # Will result in no candidates
        else:
             range_start_idx = mask_after_line # 0-based index *after* the specified line
             print(f"INFO [mask_verilog_lines]: Masking range set to lines *after* line {mask_after_line} (index {range_start_idx} onwards).")

    elif mask_start_line is not None and mask_end_line is not None:
        # Convert 1-based start/end to 0-based inclusive start/exclusive end
        range_start_idx = mask_start_line - 1
        range_end_idx = mask_end_line # Exclusive end index is end_line (since range iterates up to, but not including, end_idx)
        
        if range_start_idx >= total_lines:
             print(f"Warning [mask_verilog_lines]: 'mask_start_line' ({mask_start_line}) is beyond the last line ({total_lines}) for '{module_name_for_ref}'. No lines to mask.")
             range_start_idx = total_lines # Will result in no candidates
             range_end_idx = total_lines
        elif range_end_idx > total_lines:
             print(f"Warning [mask_verilog_lines]: 'mask_end_line' ({mask_end_line}) is beyond the last line ({total_lines}) for '{module_name_for_ref}'. Adjusting range end.")
             range_end_idx = total_lines # Adjust to actual end

        print(f"INFO [mask_verilog_lines]: Masking range set to lines {mask_start_line} to {mask_end_line} (indices {range_start_idx} to {range_end_idx-1}).")

    # Identify candidate lines for masking within the determined range
    candidate_indices = []
    for i in range(range_start_idx, range_end_idx):
        line = lines[i]
        stripped_line = line.strip()
        # Same exclusion logic as before
        if not stripped_line: continue
        if stripped_line.startswith("//") and not any(c.isalnum() for c in stripped_line[2:]): continue
        if stripped_line.startswith("/*") and stripped_line.endswith("*/") and stripped_line.count("/*") == 1 and stripped_line.count("*/") == 1: continue
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
           low_stripped_line.startswith("always") or \
           low_stripped_line.startswith("begin ") or \
           low_stripped_line.startswith("end ") or \
           low_stripped_line.startswith("initial"):
            continue
        candidate_indices.append(i) # Store the 0-based index

    if not candidate_indices:
        print(f"Warning [mask_verilog_lines]: No candidate lines found for masking in the specified range ({range_start_idx} to {range_end_idx-1}) for '{module_name_for_ref}' file {input_rtl_path}")
        with open(output_masked_rtl_path, 'w') as f: # Write original if no candidates
            f.writelines(lines)
        return True

    actual_num_to_mask = min(num_lines_to_mask, len(candidate_indices))
    if num_lines_to_mask > len(candidate_indices):
        print(f"Warning [mask_verilog_lines]: Requested to mask {num_lines_to_mask} lines for '{module_name_for_ref}' within the range, "
              f"but only {len(candidate_indices)} candidate lines available. Masking all {actual_num_to_mask} candidates.")

    lines_to_mask_indices = sorted(random.sample(candidate_indices, actual_num_to_mask))

    masked_lines_content = list(lines)
    print(f"INFO [mask_verilog_lines]: For module '{module_name_for_ref}', masking lines at original indices (1-based):")
    for index in lines_to_mask_indices:
        original_line_content = masked_lines_content[index].strip()
        leading_whitespace = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
        masked_lines_content[index] = leading_whitespace + mask_token + "\n"
        print(f"  Line {index + 1}: '{original_line_content}'  =>  '{mask_token}'")

    try:
        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_masked_rtl_path), exist_ok=True)
        with open(output_masked_rtl_path, 'w') as f:
            f.writelines(masked_lines_content)
        print(f"INFO [mask_verilog_lines]: Masked RTL for '{module_name_for_ref}' saved to: {output_masked_rtl_path}")
        return True
    except IOError as e:
        print(f"Error [mask_verilog_lines]: Could not write masked RTL for '{module_name_for_ref}' to {output_masked_rtl_path}: {e}")
        return False

# Example Usage (add this within the masking_utils.py file for standalone testing)
if __name__ == '__main__':
    dummy_input_path = "dummy_mask_input_range.v"
    dummy_output_path_range = "dummy_mask_output_range_masked.v"
    dummy_output_path_after = "dummy_mask_output_after_masked.v"

    dummy_rtl_content = """// 1
module test_range ( // 2
    input wire clk, // 3
    input wire rst, // 4
    output wire q1, // 5
    output wire q2  // 6
); // 7
    // Comment // 8
    reg r1; // 9
    reg r2; // 10
    
    assign q1 = r1; // 11 - Candidate
    assign q2 = r2; // 12 - Candidate

    always @(posedge clk) begin // 13
        r1 <= ~r1; // 14 - Candidate
    end // 15
    
    always @(posedge clk) begin // 16
        r2 <= r1; // 17 - Candidate
    end // 18
endmodule // 19
"""
    with open(dummy_input_path, "w") as f:
        f.write(dummy_rtl_content)

    print("\n--- Testing mask between lines 11 and 14 ---")
    success_range = mask_verilog_lines(
        dummy_input_path,
        dummy_output_path_range,
        num_lines_to_mask=2,
        mask_start_line=11,
        mask_end_line=14, # Should consider lines 11, 12, 13, 14
                          # Candidates are indices 10 (line 11), 11 (line 12), 13 (line 14)
        seed=1,
        module_name_for_ref="test_range_dummy"
    )
    if success_range:
        with open(dummy_output_path_range, 'r') as f: print(f.read())
    else: print("Range masking failed.")

    print("\n--- Testing mask after line 12 ---")
    success_after = mask_verilog_lines(
        dummy_input_path,
        dummy_output_path_after,
        num_lines_to_mask=1,
        mask_after_line=12, # Should consider lines 13 onwards
                            # Candidates are indices 13 (line 14), 16 (line 17)
        seed=2,
        module_name_for_ref="test_after_dummy"
    )
    if success_after:
        with open(dummy_output_path_after, 'r') as f: print(f.read())
    else: print("After masking failed.")

    # Clean up dummy files
    if os.path.exists(dummy_input_path): os.remove(dummy_input_path)
    if os.path.exists(dummy_output_path_range): os.remove(dummy_output_path_range)
    if os.path.exists(dummy_output_path_after): os.remove(dummy_output_path_after)