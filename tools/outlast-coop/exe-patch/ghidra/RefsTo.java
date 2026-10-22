// Lists the functions that reference each given address (hex), with the referencing instruction address.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class RefsTo extends GhidraScript {
    @Override
    public void run() throws Exception {
        for (String s : getScriptArgs()) {
            Address ad = toAddr(s);
            println("REFS TO " + s);
            ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(ad);
            java.util.TreeMap<String,String> m = new java.util.TreeMap<>();
            while (it.hasNext()) {
                Reference r = it.next();
                Function f = getFunctionContaining(r.getFromAddress());
                String k = f == null ? "?" : f.getEntryPoint().toString();
                m.merge(k, r.getFromAddress() + (r.getReferenceType().isWrite() ? "(w)" : ""), (a, b) -> a + "," + b);
            }
            for (var e : m.entrySet()) println("  fn " + e.getKey() + " via " + e.getValue());
        }
    }
}
