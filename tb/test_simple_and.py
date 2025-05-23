# verilog-i2c/tb/test_simple_and.py
from myhdl import *
import os
import sys # For exiting on error

# --- MyHDL Testbench for simple_and ---


# This name is used to find the Verilog wrapper (test_simple_and.v)
# and the compiled output (test_simple_and.vvp)
testbench_verilog_wrapper_name = 'test_simple_and'
# This is the name of the DUT module the LLM should generate (e.g., "simple_and")
# and also the name of the Verilog file the LLM generates (e.g., "simple_and.v")
dut_module_name = 'simple_and'

srcs = []

# This environment variable will be set by evaluate_rtl.sh
# It points to the Verilog file generated by the LLM.
# DUT_ENV_VAR_NAME is also passed to evaluate_rtl.sh by run_experiment.py
default_dut_path = os.path.join(os.path.dirname(__file__), "..", "rtl", "%s.v" % dut_module_name)
dut_rtl_env_var_name = os.environ.get("DUT_RTL_FILE_SIMPLE_AND", default_dut_path)
if dut_rtl_env_var_name == default_dut_path:
    generated_dut_rtl_file = default_dut_path
else:
    #generated_dut_rtl_file = os.environ.get(dut_rtl_env_var_name)
    generated_dut_rtl_file = dut_rtl_env_var_name

if generated_dut_rtl_file is None:
    print(f"ERROR: Environment variable '{dut_rtl_env_var_name}' (for DUT RTL file) is not set.")
    print(f"       This script should be called by 'evaluate_rtl.sh' which sets this variable.")
    sys.exit(1)

if not os.path.isabs(generated_dut_rtl_file):
    print(f"Warning: DUT RTL file path '{generated_dut_rtl_file}' from env var '{dut_rtl_env_var_name}' is not absolute. Assuming it's findable by iverilog.")
    # For robustness, realpath is used in evaluate_rtl.sh, so it should be absolute here.

if not os.path.exists(generated_dut_rtl_file):
    print(f"ERROR: DUT RTL file specified by '{dut_rtl_env_var_name}' does not exist at '{generated_dut_rtl_file}'")
    sys.exit(1)

print(f"MyHDL Test for '{dut_module_name}': Using DUT RTL file: {generated_dut_rtl_file}")

# Add the LLM-generated DUT Verilog file to sources for compilation
srcs.append(generated_dut_rtl_file)
# Add the Verilog testbench wrapper (test_simple_and.v)
# Assumes test_simple_and.v is in the same directory as this Python script
srcs.append(os.path.join(os.path.dirname(__file__), f"{testbench_verilog_wrapper_name}.v"))

src_files_str = ' '.join(f'"{s}"' for s in srcs) # Enclose paths in quotes for safety
# Output compiled file in the current directory (which will be tb/ when run by evaluate_rtl.sh)
compiled_output_name = f"{testbench_verilog_wrapper_name}.vvp"
build_cmd = f"iverilog -o {compiled_output_name} {src_files_str}"

print(f"MyHDL Test: Build command: {build_cmd}")

def simple_and_myhdl_tb():
    # Signals to connect to the Verilog wrapper
    clk = Signal(bool(0)) # Dummy clock - MyHDL Cosimulation often expects one
    a   = Signal(bool(0)) # Input 'a' to the AND gate
    b   = Signal(bool(0)) # Input 'b' to the AND gate
    y   = Signal(bool(0)) # Output 'y' from the AND gate

    # Compile Verilog source files using Icarus Verilog
    print("MyHDL Test: Compiling Verilog sources...")
    compile_status = os.system(build_cmd)
    if compile_status != 0:
        print(f"MyHDL Test: FATAL - Verilog compilation failed with status {compile_status}. Command was: {build_cmd}")
        raise Exception("Verilog compilation error")
    print("MyHDL Test: Verilog compilation successful.")

    # Instantiate the co-simulation object
    # The first argument to Cosimulation is the command to run the compiled Verilog
    # Make sure myhdl.vpi can be found (via IVERILOG_VPI_MODULE_PATH)
    print(f"MyHDL Test: Starting Cosimulation with 'vvp -m myhdl {compiled_output_name}'")
    dut_cosim = Cosimulation(
        f"vvp -m myhdl {compiled_output_name}", # Can add -lxt2 here for waveform dump
        # Signal mapping: MyHDL signal = Verilog port name in wrapper
        clk_myhdl=clk, # Maps MyHDL 'clk' to Verilog 'clk_myhdl' in test_simple_and.v
        a_myhdl=a,     # Maps MyHDL 'a' to Verilog 'a_myhdl'
        b_myhdl=b,     # Maps MyHDL 'b' to Verilog 'b_myhdl'
        y_to_myhdl=y   # Maps Verilog 'y_to_myhdl' to MyHDL 'y'
    )

    # Dummy clock generator (not strictly needed for combinational logic like AND,
    # but good practice for co-simulation structure and if delays are used)
    @always(delay(5))
    def clk_driver():
        clk.next = not clk

    # Stimulus and checking process
    @instance
    def stimulus_checker():
        print("MyHDL Test: Stimulus started.")
        test_vectors = [
            # (input_a, input_b, expected_output_y)
            (0, 0, 0),
            (0, 1, 0),
            (1, 0, 0),
            (1, 1, 1),
        ]

        for i_a, i_b, expected_y_val in test_vectors:
            a.next = bool(i_a)
            b.next = bool(i_b)
            
            yield delay(2) # Give a small delay for values to propagate in simulation
                           # Even for combinational logic, this helps ensure value is read after update.

            # Read the output 'y' from the DUT
            current_y_val = int(y) # Convert MyHDL bool Signal to int for comparison/printing
            
            print(f"MyHDL Test: Inputs a={i_a}, b={i_b}. DUT y={current_y_val}. Expected y={expected_y_val}.")
            
            assert current_y_val == expected_y_val, \
                f"Test Failed! For a={i_a}, b={i_b}: DUT y={current_y_val}, Expected={expected_y_val}"
            
            yield delay(2) # Hold inputs for a bit

        print("MyHDL Test: All test vectors PASSED successfully!")
        raise StopSimulation # End the MyHDL simulation

    return instances() # Return all generators (clk_driver, stimulus_checker) and the Cosimulation instance

# Main function to run the simulation
if __name__ == '__main__':
    print(f"--- Running MyHDL Testbench: {os.path.basename(__file__)} ---")
    # This will create a Simulation object from the generators returned by simple_and_myhdl_tb()
    # and then run it.
    try:
        sim = Simulation(simple_and_myhdl_tb())
        sim.run()
        print(f"--- MyHDL Testbench: {os.path.basename(__file__)} COMPLETED SUCCESSFULLY ---")
    except Exception as e:
        print(f"--- MyHDL Testbench: {os.path.basename(__file__)} FAILED ---")
        print(f"Error: {e}")
        # Re-raise the exception so that evaluate_rtl.sh sees a non-zero exit code
        raise