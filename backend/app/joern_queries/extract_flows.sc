// extract_flows.sc
// Extracts data flow paths from identified source nodes
// Usage: joern --script extract_flows.sc --param cpgFile=<path> --param sourceIdsFile=<path>

import io.shiftleft.semanticcpg.language._
import io.joern.dataflowengineoss.language._
import scala.io.Source
import scala.util.{Try, Using}

@main def main(cpgFile: String, sourceIdsFile: String): Unit = {
  loadCpg(cpgFile)

  // Read source IDs from file
  val idsJson = Using(Source.fromFile(sourceIdsFile))(_.mkString).getOrElse("[]")
  val sourceIds = idsJson.stripPrefix("[").stripSuffix("]").split(",").map(_.trim.toLong).toList

  val sinkPatterns = List(
    "strcpy", "strcat", "sprintf", "gets", "scanf",
    "memcpy", "memmove", "system", "exec", "popen",
    "eval", "query", "execute", "send", "write",
    "printf", "fprintf", "snprintf"
  )

  val flows = sourceIds.flatMap { sourceId =>
    Try {
      // Create fresh traversals for each source ID
      val sources = cpg.all.id(sourceId)
      val sinks = cpg.call.filter(c => sinkPatterns.exists(p => c.name.contains(p)))

      // reachableByFlows works on traversals, not individual nodes
      val reachableFlows = sinks.reachableByFlows(sources).l

      reachableFlows.map { flow =>
        val pathNodes = flow.elements.map { elem =>
          val loc = elem.location
          val file = loc.filename
          val line = loc.lineNumber.getOrElse(-1)
          s"""{"id": ${elem.id}, "code": "${esc(elem.properties.getOrElse("CODE", "").toString)}", "file": "${esc(file)}", "line": ${line}}"""
        }
        val lastElem = flow.elements.last
        val sinkName = lastElem.properties.getOrElse("NAME", "unknown").toString
        val sinkCode = lastElem.properties.getOrElse("CODE", "").toString
        s"""{"source_id": ${sourceId}, "sink": "${esc(sinkName)}", "sink_code": "${esc(sinkCode)}", "path": [${pathNodes.mkString(",")}]}"""
      }
    }.getOrElse(List.empty)
  }

  println(s"[${flows.mkString(",")}]")
}

def esc(s: String): String = {
  s.replace("\\", "\\\\")
   .replace("\"", "\\\"")
   .replace("\n", "\\n")
   .replace("\r", "\\r")
   .replace("\t", "\\t")
}
