// Finds strings (ASCII and UTF-16) in the program and prints each address with the functions that reference it.
// args: one or more substrings
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.mem.*;
import java.util.*;

public class FindStr extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Memory mem = currentProgram.getMemory();
        for (String s : a) {
            for (byte[] pat : new byte[][]{ s.getBytes("US-ASCII"), s.getBytes("UTF-16LE") }) {
                Address start = mem.getMinAddress();
                int found = 0;
                while (start != null && found < 20) {
                    Address hit = mem.findBytes(start, pat, null, true, monitor);
                    if (hit == null) break;
                    found++;
                    StringBuilder sb = new StringBuilder();
                    sb.append("STR '").append(s).append("' ").append(pat.length == s.length() ? "A" : "W").append(" @ ").append(hit);
                    int step = pat.length == s.length() ? 1 : 2;
                    Address st = hit;
                    for (int k = 0; k < 400; k++) {
                        Address prev = st.subtract(step);
                        byte b0 = mem.getByte(prev);
                        byte b1 = step == 2 ? mem.getByte(prev.add(1)) : 0;
                        if (b0 == 0 && b1 == 0) break;
                        st = prev;
                    }
                    sb.append(" (string starts ").append(st).append(")");
                    ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(st);
                    int n = 0;
                    while (it.hasNext() && n < 12) {
                        Reference r = it.next();
                        Function f = getFunctionContaining(r.getFromAddress());
                        sb.append("\n    ref from ").append(r.getFromAddress()).append(" in ").append(f == null ? "?" : f.getName() + " @ " + f.getEntryPoint());
                        n++;
                    }
                    println(sb.toString());
                    start = hit.add(1);
                }
            }
        }
    }
}
