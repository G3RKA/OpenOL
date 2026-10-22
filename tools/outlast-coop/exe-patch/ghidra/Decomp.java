// Decompiles the functions containing the given addresses (hex, e.g. 140123456) and prints C-like text plus the callers.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class Decomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        for (String s : getScriptArgs()) {
            Address ad = toAddr(s);
            Function f = getFunctionContaining(ad);
            if (f == null) { println("NO FUNCTION at " + s); continue; }
            println("==== " + f.getName() + " @ " + f.getEntryPoint() + " size " + f.getBody().getNumAddresses());
            ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint());
            int n = 0;
            while (it.hasNext() && n < 10) { Reference r = it.next(); Function c = getFunctionContaining(r.getFromAddress()); println("  called from " + r.getFromAddress() + " in " + (c == null ? "?" : c.getName() + " @ " + c.getEntryPoint())); n++; }
            DecompileResults res = di.decompileFunction(f, 120, monitor);
            if (res.decompileCompleted()) println(res.getDecompiledFunction().getC());
            else println("decompile failed: " + res.getErrorMessage());
        }
    }
}
