// tb_trojan.v  -- auto-generated self-checking testbench (Icarus Verilog)
// Streams vec_in.mem through a clean twin (TROJAN_EN=0) and a Trojaned twin
// (TROJAN_EN=1) and checks: clean twin == vec_clean.mem for EVERY sample
// (baseline), and Trojaned twin == vec_troj.mem (arms on the tone, then bypass).
`timescale 1ns/1ps
`include "params.vh"
module tb_trojan;
    reg clk=0, rst_n=0, in_valid=0;
    reg  signed [15:0] xin;
    wire signed [15:0] yc, yt;
    wire vc, vt;
    always #5 clk = ~clk;

    fir_core        #(.TROJAN_EN(0)) uClean (.clk(clk),.rst_n(rst_n),.in_valid(in_valid),.x(xin),.y(yc),.out_valid(vc));
    fir_core_trojan #(.TROJAN_EN(1)) uTroj  (.clk(clk),.rst_n(rst_n),.in_valid(in_valid),.x(xin),.y(yt),.out_valid(vt));

    reg signed [15:0] vin   [0:`NVEC-1];
    reg signed [15:0] vclean[0:`NVEC-1];
    reg signed [15:0] vtroj [0:`NVEC-1];
    integer n, errc, errt, oc, ot;
    initial begin
        $readmemh("vec_in.mem", vin);
        $readmemh("vec_clean.mem", vclean);
        $readmemh("vec_troj.mem", vtroj);
        errc=0; errt=0; oc=0; ot=0;
        @(negedge clk); rst_n=1;
        for (n=0; n<`NVEC; n=n+1) begin
            @(negedge clk); in_valid=1; xin=vin[n];
            @(posedge clk);                 // out_valid asserts for this sample
            #1;
            if (vc) begin
                if (yc !== vclean[oc]) begin errc=errc+1;
                    if (errc<=5) $display("CLEAN mismatch @%0d: got %0d exp %0d", oc, yc, vclean[oc]); end
                oc=oc+1;
            end
            if (vt) begin
                if (yt !== vtroj[ot]) begin errt=errt+1;
                    if (errt<=5) $display("TROJ  mismatch @%0d: got %0d exp %0d", ot, yt, vtroj[ot]); end
                ot=ot+1;
            end
        end
        @(negedge clk); in_valid=0;
        $display("checked clean=%0d troj=%0d  errors clean=%0d troj=%0d", oc, ot, errc, errt);
        if (errc==0 && errt==0 && oc==`NVEC && ot==`NVEC)
            $display("TB_TROJAN: ALL PASS");
        else
            $display("TB_TROJAN: FAIL");
        $finish;
    end
endmodule
