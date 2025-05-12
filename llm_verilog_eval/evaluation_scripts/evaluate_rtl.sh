#!/bin/bash
# llm_verilog_eval/evaluation_scripts/evaluate_rtl.sh

GENERATED_RTL_FILE=$1
TESTBENCH_SCRIPT_NAME_ARG=$2 # e.g., test_simple_and.py or test_i2c_init.py
DUT_ENV_VAR_NAME_ARG=$3      # e.g., DUT_RTL_FILE_SIMPLE_AND or DUT_RTL_FILE_I2C_INIT
LOG_FILE_ARG=$4

# --- Configuration ---
PROJECT_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../" && pwd)"
TB_DIR="${PROJECT_ROOT_DIR}/tb"
# IMPORTANT: Ensure this path is correct for your setup
DEFAULT_MYHDL_VPI_PATH="/data/genai/kmcho/custom_env/myhdl_customEnv_install/myhdl/cosimulation/icarus/"
# --- End Configuration ---

# Validate required arguments
if [ -z "$GENERATED_RTL_FILE" ] || [ -z "$TESTBENCH_SCRIPT_NAME_ARG" ] || [ -z "$DUT_ENV_VAR_NAME_ARG" ]; then
    echo "Usage: $0 <path_to_generated_rtl.v> <testbench_script.py> <DUT_ENV_VAR_NAME> [path_to_log_file]"
    exit 1
fi

# Check if IVERILOG_VPI_MODULE_PATH is set, otherwise use default
if [ -z "$IVERILOG_VPI_MODULE_PATH" ]; then
    echo "INFO: IVERILOG_VPI_MODULE_PATH is not set in the environment."
    echo "      Attempting to use default VPI path: $DEFAULT_MYHDL_VPI_PATH"
    if [ -d "$DEFAULT_MYHDL_VPI_PATH" ]; then
        export IVERILOG_VPI_MODULE_PATH="$DEFAULT_MYHDL_VPI_PATH"
        echo "      Set IVERILOG_VPI_MODULE_PATH to: $IVERILOG_VPI_MODULE_PATH"
    else
        echo "ERROR: Default VPI path '$DEFAULT_MYHDL_VPI_PATH' not found or not a directory."
        echo "       Please set IVERILOG_VPI_MODULE_PATH environment variable correctly."
        exit 1
    fi
fi

# Validate file and directory existence
if [ ! -f "$GENERATED_RTL_FILE" ]; then
    echo "Error: Generated RTL file not found at '$GENERATED_RTL_FILE'"
    exit 1
fi
if [ ! -d "$TB_DIR" ]; then
    echo "Error: Testbench directory not found at '$TB_DIR'"
    exit 1
fi
FULL_TESTBENCH_SCRIPT_PATH="${TB_DIR}/${TESTBENCH_SCRIPT_NAME_ARG}"
if [ ! -f "$FULL_TESTBENCH_SCRIPT_PATH" ]; then
    echo "Error: Testbench script not found at '$FULL_TESTBENCH_SCRIPT_PATH'"
    exit 1
fi

# Export the environment variable that the MyHDL testbench script will use
# Use realpath to ensure an absolute path is passed, which is generally safer.
export "$DUT_ENV_VAR_NAME_ARG"="$(realpath "$GENERATED_RTL_FILE")"
echo "INFO: Exported $DUT_ENV_VAR_NAME_ARG=${!DUT_ENV_VAR_NAME_ARG}" # Print the value of the exported var

# Change to the testbench directory before running the Python script
# This ensures that relative paths within the MyHDL script (e.g., for its own Verilog wrapper) work correctly.
echo "INFO: Changing current directory to $TB_DIR"
cd "$TB_DIR" || { echo "Error: Failed to change directory to $TB_DIR"; exit 1; }

echo "----------------------------------------------------------------------"
echo "Evaluating DUT: $(basename "$GENERATED_RTL_FILE") (Path: ${!DUT_ENV_VAR_NAME_ARG})"
echo "Using Testbench: $TESTBENCH_SCRIPT_NAME_ARG (in $PWD)"
echo "MyHDL VPI Path: $IVERILOG_VPI_MODULE_PATH"
[ -n "$LOG_FILE_ARG" ] && echo "Log file: $LOG_FILE_ARG"
echo "----------------------------------------------------------------------"

# Run the MyHDL testbench
if [ -n "$LOG_FILE_ARG" ]; then
    # Ensure the directory for the log file exists (log file path is absolute from run_experiment.py)
    mkdir -p "$(dirname "$LOG_FILE_ARG")"
    echo "INFO: Running MyHDL test (output to $LOG_FILE_ARG)..."
    python3 "$TESTBENCH_SCRIPT_NAME_ARG" > "$LOG_FILE_ARG" 2>&1
else
    echo "INFO: Running MyHDL test (output to console)..."
    python3 "$TESTBENCH_SCRIPT_NAME_ARG"
fi
RESULT=$?

# Optional: cd back to original directory
# ORIGINAL_DIR="$(cd - >/dev/null && pwd)"
# echo "INFO: Changed back to $ORIGINAL_DIR"

if [ $RESULT -eq 0 ]; then
    echo "----------------------------------------------------------------------"
    echo "PASS: Evaluation successful for $(basename "$GENERATED_RTL_FILE")"
    echo "----------------------------------------------------------------------"
    exit 0
else
    echo "----------------------------------------------------------------------"
    echo "FAIL: Evaluation failed for $(basename "$GENERATED_RTL_FILE") (MyHDL script exit code: $RESULT)"
    [ -n "$LOG_FILE_ARG" ] && echo "      Check log for details: $LOG_FILE_ARG"
    echo "----------------------------------------------------------------------"
    exit 1
fi