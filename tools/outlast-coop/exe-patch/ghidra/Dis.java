// Prints N instructions (with bytes) starting at each "addr:count" argument.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;

public class Dis extends GhidraScript {
    @Override
    public void run() throws Exception {
        for (String s : getScriptArgs()) {
            String[] p = s.split(":");
            Address a = toAddr(p[0]);
            int n = Integer.parseInt(p[1]);
            println("DIS " + s);
            Instruction ins = getInstructionAt(a);
            if (ins == null) { ins = getInstructionContaining(a); }
            for (int i = 0; i < n && ins != null; i++) {
                StringBuilder b = new StringBuilder();
                for (byte x : ins.getBytes()) b.append(String.format("%02x ", x));
                println(String.format("  %s  %-22s %s", ins.getAddress(), b.toString().trim(), ins.toString()));
                ins = ins.getNext();
            }
        }
    }
}
