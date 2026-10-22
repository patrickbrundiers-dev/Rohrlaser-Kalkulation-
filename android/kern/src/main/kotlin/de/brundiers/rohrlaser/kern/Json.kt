package de.brundiers.rohrlaser.kern

/**
 * Kleiner JSON-Leser und -Schreiber ohne fremde Bibliothek (Rechenkern läuft auf Android und in den Tests ohne
 * Android). Ergebnis: Map (Reihenfolge erhalten), List, String, Double, Boolean oder null.
 */
object Json {
    fun lies(text: String): Any? {
        val l = Leser(text)
        val wert = l.wert()
        l.leer()
        require(l.i == text.length) { "JSON: unerwartetes Zeichen an Stelle ${l.i}" }
        return wert
    }

    private class Leser(val s: String) {
        var i = 0

        fun leer() {
            while (i < s.length && s[i].isWhitespace()) i++
        }

        fun wert(): Any? {
            leer()
            require(i < s.length) { "JSON: Ende erreicht" }
            return when (val c = s[i]) {
                '{' -> objekt()
                '[' -> liste()
                '"' -> text()
                't' -> wort("true", true)
                'f' -> wort("false", false)
                'n' -> wort("null", null)
                else -> if (c == '-' || c.isDigit()) zahl() else throw IllegalArgumentException("JSON: '$c' an Stelle $i")
            }
        }

        fun wort(w: String, v: Any?): Any? {
            require(s.startsWith(w, i)) { "JSON: $w erwartet an Stelle $i" }
            i += w.length
            return v
        }

        fun objekt(): Map<String, Any?> {
            val m = LinkedHashMap<String, Any?>()
            i++
            leer()
            if (s[i] == '}') { i++; return m }
            while (true) {
                leer()
                val k = text()
                leer()
                require(s[i] == ':') { "JSON: ':' erwartet an Stelle $i" }
                i++
                m[k] = wert()
                leer()
                if (s[i] == ',') { i++; continue }
                require(s[i] == '}') { "JSON: '}' erwartet an Stelle $i" }
                i++
                return m
            }
        }

        fun liste(): List<Any?> {
            val l = ArrayList<Any?>()
            i++
            leer()
            if (s[i] == ']') { i++; return l }
            while (true) {
                l.add(wert())
                leer()
                if (s[i] == ',') { i++; continue }
                require(s[i] == ']') { "JSON: ']' erwartet an Stelle $i" }
                i++
                return l
            }
        }

        fun text(): String {
            require(s[i] == '"') { "JSON: Text erwartet an Stelle $i" }
            i++
            val b = StringBuilder()
            while (true) {
                val c = s[i++]
                when (c) {
                    '"' -> return b.toString()
                    '\\' -> {
                        when (val e = s[i++]) {
                            'n' -> b.append('\n'); 't' -> b.append('\t'); 'r' -> b.append('\r')
                            'b' -> b.append('\b'); 'f' -> b.append('\u000C')
                            'u' -> { b.append(s.substring(i, i + 4).toInt(16).toChar()); i += 4 }
                            else -> b.append(e)
                        }
                    }
                    else -> b.append(c)
                }
            }
        }

        fun zahl(): Double {
            val start = i
            while (i < s.length && (s[i].isDigit() || s[i] in "+-.eE")) i++
            return s.substring(start, i).toDouble()
        }
    }

    fun schreibe(wert: Any?): String = StringBuilder().also { schreibe(wert, it) }.toString()

    private fun schreibe(w: Any?, b: StringBuilder) {
        when (w) {
            null -> b.append("null")
            is Boolean -> b.append(w)
            is Int, is Long -> b.append(w)
            is Number -> {
                val d = w.toDouble()
                if (d == Math.floor(d) && kotlin.math.abs(d) < 1e15) b.append(d.toLong()) else b.append(d)
            }
            is String -> {
                b.append('"')
                for (c in w) when {
                    c == '"' -> b.append("\\\"")
                    c == '\\' -> b.append("\\\\")
                    c == '\n' -> b.append("\\n")
                    c < ' ' -> b.append(String.format("\\u%04x", c.code))
                    else -> b.append(c)
                }
                b.append('"')
            }
            is Map<*, *> -> {
                b.append('{')
                var erst = true
                for ((k, v) in w) {
                    if (!erst) b.append(',')
                    erst = false
                    schreibe(k.toString(), b)
                    b.append(':')
                    schreibe(v, b)
                }
                b.append('}')
            }
            is Iterable<*> -> {
                b.append('[')
                var erst = true
                for (v in w) {
                    if (!erst) b.append(',')
                    erst = false
                    schreibe(v, b)
                }
                b.append(']')
            }
            else -> throw IllegalArgumentException("JSON: kann ${w::class} nicht schreiben")
        }
    }
}
