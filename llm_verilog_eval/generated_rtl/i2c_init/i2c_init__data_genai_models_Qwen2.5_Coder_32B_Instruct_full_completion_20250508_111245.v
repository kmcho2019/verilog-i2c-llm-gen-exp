// llm_verilog_eval/prompts/i2c_init/full_completion_header.v
/*
 * I2C init
 */
module i2c_init (
    input  wire        clk,
    input  wire        rst,

    /*
     * I2C master interface
     */
    output wire [6:0]  m_axis_cmd_address,
    output wire        m_axis_cmd_start,
    output wire        m_axis_cmd_read,
    output wire        m_axis_cmd_write,
    output wire        m_axis_cmd_write_multiple,
    output wire        m_axis_cmd_stop,
    output wire        m_axis_cmd_valid,
    input  wire        m_axis_cmd_ready,

    output wire [7:0]  m_axis_data_tdata,
    output wire        m_axis_data_tvalid,
    input  wire        m_axis_data_tready,
    output wire        m_axis_data_tlast,

    /*
     * Status
     */
    output wire        busy,

    /*
     * Configuration
     */
    input  wire        start
);

    // Internal signals
    reg [6:0]          cmd_address;
    reg                cmd_start;
    reg                cmd_read;
    reg                cmd_write;
    reg                cmd_write_multiple;
    reg                cmd_stop;
    reg                cmd_valid;
    reg [7:0]          data_tdata;
    reg                data_tvalid;
    reg                data_tlast;

    // State machine states
    typedef enum reg [3:0] {
        IDLE,
        START_INIT,
        SEND_ADDRESS,
        SEND_DATA,
        STOP_I2C,
        DELAY,
        DONE
    } state_t;

    state_t            state, next_state;

    // Initialization data ROM
    reg [7:0] init_data [0:15]; // Example size, can be adjusted
    integer i;
    initial begin
        for (i = 0; i < 16; i = i + 1) begin
            init_data[i] = 8'h00; // Initialize with default values
        end
        // Populate with actual initialization sequence
        init_data[0] = 8'h55; // Example data
        init_data[1] = 8'hAA; // Example data
        // Add more initialization data as needed
    end

    // State machine registers
    reg [3:0]          seq_index;
    reg [7:0]          delay_counter;

    // State machine logic
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= IDLE;
            seq_index <= 4'b0000;
            delay_counter <= 8'b00000000;
            cmd_address <= 7'b0000000;
            cmd_start <= 1'b0;
            cmd_read <= 1'b0;
            cmd_write <= 1'b0;
            cmd_write_multiple <= 1'b0;
            cmd_stop <= 1'b0;
            cmd_valid <= 1'b0;
            data_tdata <= 8'b00000000;
            data_tvalid <= 1'b0;
            data_tlast <= 1'b0;
        end else begin
            state <= next_state;
            case (state)
                IDLE: begin
                    if (start) begin
                        seq_index <= 4'b0000;
                        next_state <= START_INIT;
                    end else begin
                        next_state <= IDLE;
                    end
                end
                START_INIT: begin
                    cmd_address <= init_data[seq_index];
                    cmd_start <= 1'b1;
                    cmd_valid <= 1'b1;
                    if (m_axis_cmd_ready) begin
                        cmd_start <= 1'b0;
                        cmd_valid <= 1'b0;
                        seq_index <= seq_index + 1;
                        next_state <= SEND_ADDRESS;
                    end else begin
                        next_state <= START_INIT;
                    end
                end
                SEND_ADDRESS: begin
                    cmd_address <= init_data[seq_index];
                    cmd_write <= 1'b1;
                    cmd_valid <= 1'b1;
                    if (m_axis_cmd_ready) begin
                        cmd_write <= 1'b0;
                        cmd_valid <= 1'b0;
                        seq_index <= seq_index + 1;
                        next_state <= SEND_DATA;
                    end else begin
                        next_state <= SEND_ADDRESS;
                    end
                end
                SEND_DATA: begin
                    data_tdata <= init_data[seq_index];
                    data_tvalid <= 1'b1;
                    if (m_axis_data_tready) begin
                        data_tvalid <= 1'b0;
                        seq_index <= seq_index + 1;
                        if (init_data[seq_index] == 8'hFF) begin // End of data marker
                            seq_index <= seq_index + 1;
                            next_state <= STOP_I2C;
                        end else begin
                            next_state <= SEND_DATA;
                        end
                    end else begin
                        next_state <= SEND_DATA;
                    end
                end
                STOP_I2C: begin
                    cmd_stop <= 1'b1;
                    cmd_valid <= 1'b1;
                    if (m_axis_cmd_ready) begin
                        cmd_stop <= 1'b0;
                        cmd_valid <= 1'b0;
                        seq_index <= seq_index + 1;
                        if (seq_index >= 16) begin // End of sequence
                            next_state <= DONE;
                        end else begin
                            next_state <= START_INIT;
                        end
                    end else begin
                        next_state <= STOP_I2C;
                    end
                end
                DELAY: begin
                    if (delay_counter < 8'd255) begin
                        delay_counter <= delay_counter + 1;
                        next_state <= DELAY;
                    end else begin
                        delay_counter <= 8'b00000000;
                        seq_index <= seq_index + 1;
                        next_state <= START_INIT;
                    end
                end
                DONE: begin
                    next_state <= IDLE;
                end
                default: begin
                    next_state <= IDLE;
                end
            endcase
        end
    end

    // Output assignments
    assign m_axis_cmd_address = cmd_address;
    assign m_axis_cmd_start = cmd_start;
    assign m_axis_cmd_read = cmd_read;
    assign m_axis_cmd_write = cmd_write;
    assign m_axis_cmd_write_multiple = cmd_write_multiple;
    assign m_axis_cmd_stop = cmd_stop;
    assign m_axis_cmd_valid = cmd_valid;
    assign m_axis_data_tdata = data_tdata;
    assign m_axis_data_tvalid = data_tvalid;
    assign m_axis_data_tlast = data_tlast;
    assign busy = (state != IDLE);

endmodule