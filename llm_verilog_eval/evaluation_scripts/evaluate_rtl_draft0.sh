#!/bin/bash
# llm_verilog_eval/evaluation_scripts/evaluate_rtl.sh

GENERATED_RTL_FILE=$1
TESTBENCH_SCRIPT_NAME="test_i2c_init.py" # Specific to this module for now
DUT_ENV_VAR_NAME="DUT_RTL_FILE_I2C_INIT" # Must match the one in test_i2c_init.py
LOG_FILE_ARG=$2


# --- Configuration ---
# Absolute path to the directory containing your testbench scripts (tb/)
# Assuming this script (evaluate_rtl.sh) is in llm_verilog_eval/evaluation_scripts/
# Adjust if your structure is different.
PROJECT_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../" && pwd)" # Navigates two levels up from script dir
TB_DIR="${PROJECT_ROOT_DIR}/tb"

# Ensure IVERILOG_VPI_MODULE_PATH is set (critical for MyHDL co-simulation)
# You should set this in your environment, or uncomment and set it here if needed.
# export IVERILOG_VPI_MODULE_PATH="/path/to/your/myhdl_install/myhdl/cosimulation/icarus/"
if [ -z "$IVERILOG_VPI_MODULE_PATH" ]; then
    echo "ERROR: IVERILOG_VPI_MODULE_PATH is not set. Please set it to point to your myhdl.vpi directory."
    # Attempt to set it to the path you used previously, add error checking if this is not reliable
    DEFAULT_MYHDL_VPI_PATH="/data/genai/kmcho/custom_env/myhdl_customEnv_install/myhdl/cosimulation/icarus/"
    if [ -d "$DEFAULT_MYHDL_VPI_PATH" ]; then
        echo "Attempting to use default VPI path: $DEFAULT_MYHDL_VPI_PATH"
        export IVERILOG_VPI_MODULE_PATH="$DEFAULT_MYHDL_VPI_PATH"
    else
        exit 1 # Exit if VPI path is crucial and not found
    fi
fi
# --- End Configuration ---

if [ -z "$GENERATED_RTL_FILE" ]; then
    echo "Usage: $0 <path_to_generated_rtl.v> [path_to_log_file]"
    exit 1
fi

if [ ! -f "$GENERATED_RTL_FILE" ]; then
    echo "Error: Generated RTL file not found at '$GENERATED_RTL_FILE'"
    exit 1
fi

if [ ! -d "$TB_DIR" ]; then
    echo "Error: Testbench directory not found at '$TB_DIR'"
    exit 1
fi

# Set the environment variable for the DUT RTL file (absolute path is safer)
export "$DUT_ENV_VAR_NAME"="$(realpath "$GENERATED_RTL_FILE")"

# Change to the testbench directory to run the MyHDL script
# MyHDL scripts often have relative paths for their own Verilog wrappers or other resources
cd "$TB_DIR" || { echo "Failed to cd to $TB_DIR"; exit 1; }

echo "----------------------------------------------------------------------"
echo "Evaluating DUT: $GENERATED_RTL_FILE"
echo "Using Testbench: ${TB_DIR}/${TESTBENCH_SCRIPT_NAME}"
echo "MyHDL VPI Path: $IVERILOG_VPI_MODULE_PATH"
echo "Log file (if any): $LOG_FILE_ARG"
echo "----------------------------------------------------------------------"

# Activate your Python virtual environment if not already active when calling this script
# Example: source /path/to/your/customEnv/bin/activate

# Run the MyHDL testbench
if [ -n "$LOG_FILE_ARG" ]; then
    # Ensure the directory for the log file exists
    mkdir -p "$(dirname "$LOG_FILE_ARG")"
    echo "Running MyHDL test (output to $LOG_FILE_ARG)..."
    python3 "$TESTBENCH_SCRIPT_NAME" > "$LOG_FILE_ARG" 2>&1
else
    echo "Running MyHDL test (output to console)..."
    python3 "$TESTBENCH_SCRIPT_NAME"
fi

RESULT=$?

# Go back to the original directory if needed, though for this script it might not matter
# cd - > /dev/null

if [ $RESULT -eq 0 ]; then
    echo "----------------------------------------------------------------------"
    echo "PASS: Evaluation successful for $GENERATED_RTL_FILE"
    echo "----------------------------------------------------------------------"
    exit 0
else
    echo "----------------------------------------------------------------------"
    echo "FAIL: Evaluation failed for $GENERATED_RTL_FILE (Exit code: $RESULT)"
    if [ -n "$LOG_FILE_ARG" ]; then
        echo "Check log for details: $LOG_FILE_ARG"
    fi
    echo "----------------------------------------------------------------------"
    exit 1
fi