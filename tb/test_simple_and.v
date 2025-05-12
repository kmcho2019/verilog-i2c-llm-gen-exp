// verilog-i2c/tb/test_simple_and.v
`timescale 1ns / 1ps

module test_simple_and;

// Inputs from MyHDL
reg clk_myhdl; // Dummy clock, MyHDL Cosimulation often expects a clock signal
reg a_myhdl;
reg b_myhdl;

// Output to MyHDL
wire y_to_myhdl;

initial begin
    $from_myhdl(
        clk_myhdl, // Connect to MyHDL's clk
        a_myhdl,   // Connect to MyHDL's a
        b_myhdl    // Connect to MyHDL's b
    );
    $to_myhdl(
        y_to_myhdl   // Connect to MyHDL's y
    );

    // Optional: waveform dumping for debugging
    $dumpfile("test_simple_and.lxt"); // Dumps into the tb/ directory when run
    $dumpvars(0, test_simple_and);    // Dump all signals in this wrapper and below
end

// Instantiate the DUT (Design Under Test - this will be the LLM generated simple_and.v)
// The module name *must* be "simple_and" as that's what the LLM will be asked to generate.
simple_and dut_instance (
    .a(a_myhdl),
    .b(b_myhdl),
    .y(y_to_myhdl)
);

endmodule