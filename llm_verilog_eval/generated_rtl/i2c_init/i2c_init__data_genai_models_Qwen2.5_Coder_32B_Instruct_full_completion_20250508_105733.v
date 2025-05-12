// Internal signals
    reg [3:0] state;
    reg [3:0] next_state;
    reg [7:0] init_data [0:15]; // Example ROM for initialization sequence
    reg [3:0] rom_addr;
    reg [7:0] rom_data;
    reg [3:0] cmd_count;
    reg [3:0] delay_count;

    // State definitions
    localparam IDLE = 4'b0000;
    localparam START_CMD = 4'b0001;
    localparam ADDR_CMD = 4'b0010;
    localparam DATA_CMD = 4'b0011;
    localparam DELAY = 4'b0100;
    localparam STOP_CMD = 4'b0101;
    localparam EXIT = 4'b0110;

    // Initialize ROM with example data
    initial begin
        init_data[0] = 8'b00000001; // Example command
        init_data[1] = 8'b00000010; // Example command
        // ... fill with actual initialization sequence
    end

    // State transition logic
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state <= IDLE;
            rom_addr <= 4'b0000;
            cmd_count <= 4'b0000;
            delay_count <= 4'b0000;
        end else begin
            state <= next_state;
            case (state)
                IDLE: begin
                    if (start) begin
                        rom_addr <= 4'b0000;
                        cmd_count <= 4'b0000;
                        delay_count <= 4'b0000;
                    end
                end
                START_CMD, ADDR_CMD, DATA_CMD, DELAY, STOP_CMD: begin
                    if (m_axis_cmd_ready || m_axis_data_tready) begin
                        rom_addr <= rom_addr + 1;
                        cmd_count <= cmd_count + 1;
                    end
                end
                default: begin
                    state <= IDLE;
                end
            endcase
        end
    end

    // Next state logic
    always @(*) begin
        next_state = state;
        case (state)
            IDLE: begin
                if (start) next_state = START_CMD;
            end
            START_CMD: begin
                if (m_axis_cmd_ready) next_state = ADDR_CMD;
            end
            ADDR_CMD: begin
                if (m_axis_cmd_ready) next_state = DATA_CMD;
            end
            DATA_CMD: begin
                if (m_axis_data_tready) begin
                    if (rom_data[7:4] == 4'b0000) next_state = DELAY;
                    else if (rom_data[7:4] == 4'b0001) next_state = STOP_CMD;
                    else next_state = ADDR_CMD;
                end
            end
            DELAY: begin
                if (delay_count == 4'd10) begin // Example delay count
                    delay_count <= 4'b0000;
                    next_state = DATA_CMD;
                end else begin
                    delay_count <= delay_count + 1;
                end
            end
            STOP_CMD: begin
                if (m_axis_cmd_ready) next_state = EXIT;
            end
            EXIT: begin
                next_state = IDLE;
            end
            default: begin
                next_state = IDLE;
            end
        endcase
    end

    // Output logic
    assign rom_data = init_data[rom_addr];
    assign m_axis_cmd_address = rom_data[6:0];
    assign m_axis_cmd_start = (state == START_CMD) ? 1'b1 : 1'b0;
    assign m_axis_cmd_read = 1'b0; // Not used in this example
    assign m_axis_cmd_write = (state == DATA_CMD) ? 1'b1 : 1'b0;
    assign m_axis_cmd_write_multiple = 1'b0; // Not used in this example
    assign m_axis_cmd_stop = (state == STOP_CMD) ? 1'b1 : 1'b0;
    assign m_axis_cmd_valid = (state == START_CMD || state == ADDR_CMD || state == DATA_CMD || state == STOP_CMD) ? 1'b1 : 1'b0;
    assign m_axis_data_tdata = rom_data;
    assign m_axis_data_tvalid = (state == DATA_CMD) ? 1'b1 : 1'b0;
    assign m_axis_data_tlast = (cmd_count == 4'd5) ? 1'b1 : 1'b0; // Example condition for last data
    assign busy = (state != IDLE);