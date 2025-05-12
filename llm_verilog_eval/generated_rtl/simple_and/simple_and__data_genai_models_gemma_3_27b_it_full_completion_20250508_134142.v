module simple_and (
    input wire a,
    input wire b,
    output wire y
);
// LLM: Implement the logic for a simple two-input AND gate.
// The output 'y' should be the logical AND of inputs 'a' and 'b'.
// Provide only the Verilog code to complete this module.

  assign y = a & b;

endmodule