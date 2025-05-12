// verilog-i2c/rtl/simple_and.v
// This is a reference correct implementation.
// The LLM will be asked to generate a file named simple_and.v
module simple_and (
    input wire a,
    input wire b,
    output wire y
);
    assign y = a & b;
endmodule