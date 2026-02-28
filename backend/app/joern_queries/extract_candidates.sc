// extract_candidates.sc
// Extracts function parameters and function calls from CPG
// Usage: joern --script extract_candidates.sc --param cpgFile=<path>

import io.shiftleft.semanticcpg.language._
import io.joern.dataflowengineoss.language._
import scala.util.Try

def truncCode(s: String, maxLen: Int = 8000): String = {
  if (s.length > maxLen) s.take(maxLen) + "\n// ... (truncated)"
  else s
}

@main def main(cpgFile: String): Unit = {
  loadCpg(cpgFile)

  // Extract function parameters
  val parameters = cpg.method.parameter.map { param =>
    val loc = param.location
    val file = loc.filename
    val line = loc.lineNumber.getOrElse(-1)
    val encMethod = Try(param.method).toOption
    val methodCode = encMethod.flatMap(m => Try(truncCode(m.code)).toOption).getOrElse("")
    val methodName = encMethod.flatMap(m => Try(m.name).toOption).getOrElse("")
    val methodLine = encMethod.flatMap(m => Try(m.lineNumber.getOrElse(-1)).toOption).getOrElse(-1)
    val methodLineEnd = encMethod.flatMap(m => Try(m.lineNumberEnd.getOrElse(-1)).toOption).getOrElse(-1)
    s"""{"id": ${param.id}, "name": "${esc(param.name)}", "method": "${esc(param.method.name)}", "file": "${esc(file)}", "line": ${line}, "type": "${esc(param.typeFullName)}", "method_code": "${esc(methodCode)}", "method_name": "${esc(methodName)}", "method_line": ${methodLine}, "method_line_end": ${methodLineEnd}}"""
  }.l

  // Extract function calls (potential source/sink functions)
  val calls = cpg.call.map { call =>
    val loc = call.location
    val file = loc.filename
    val line = loc.lineNumber.getOrElse(-1)
    val encMethod = Try(call.inAst.isMethod.head).toOption
    val methodCode = encMethod.flatMap(m => Try(truncCode(m.code)).toOption).getOrElse("")
    val methodName = encMethod.flatMap(m => Try(m.name).toOption).getOrElse("")
    val methodLine = encMethod.flatMap(m => Try(m.lineNumber.getOrElse(-1)).toOption).getOrElse(-1)
    val methodLineEnd = encMethod.flatMap(m => Try(m.lineNumberEnd.getOrElse(-1)).toOption).getOrElse(-1)
    s"""{"id": ${call.id}, "name": "${esc(call.name)}", "file": "${esc(file)}", "line": ${line}, "code": "${esc(call.code)}", "method_code": "${esc(methodCode)}", "method_name": "${esc(methodName)}", "method_line": ${methodLine}, "method_line_end": ${methodLineEnd}}"""
  }.l

  val result = s"""{"parameters": [${parameters.mkString(",")}], "calls": [${calls.mkString(",")}]}"""
  println(result)
}

def esc(s: String): String = {
  s.replace("\\", "\\\\")
   .replace("\"", "\\\"")
   .replace("\n", "\\n")
   .replace("\r", "\\r")
   .replace("\t", "\\t")
}
