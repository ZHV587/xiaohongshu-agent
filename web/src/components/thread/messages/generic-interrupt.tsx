import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp } from "lucide-react";

function isComplexValue(value: any): boolean {
  return Array.isArray(value) || (typeof value === "object" && value !== null);
}

function isUrl(value: any): boolean {
  if (typeof value !== "string") return false;
  try {
    new URL(value);
    return value.startsWith("http://") || value.startsWith("https://");
  } catch {
    return false;
  }
}

function renderInterruptStateItem(value: any): React.ReactNode {
  if (isComplexValue(value)) {
    return (
      <pre className="rounded-xl border border-oats-dark bg-oats-light/60 p-2.5 font-mono text-[11px] leading-relaxed text-charcoal-light overflow-x-auto max-w-full">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  } else if (isUrl(value)) {
    return (
      <a
        href={value}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all text-coral hover:underline font-medium inline-flex items-center gap-0.5"
      >
        {value}
      </a>
    );
  } else {
    return String(value);
  }
}

export function GenericInterruptView({
  interrupt,
}: {
  interrupt: Record<string, any> | Record<string, any>[];
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  const contentStr = JSON.stringify(interrupt, null, 2);
  const contentLines = contentStr.split("\n");
  const shouldTruncate = contentLines.length > 4 || contentStr.length > 500;

  // Function to truncate long string values (but preserve URLs)
  const truncateValue = (value: any): any => {
    if (typeof value === "string" && value.length > 100) {
      // Don't truncate URLs so they remain clickable
      if (isUrl(value)) {
        return value;
      }
      return value.substring(0, 100) + "...";
    }

    if (Array.isArray(value) && !isExpanded) {
      return value.slice(0, 2).map(truncateValue);
    }

    if (isComplexValue(value) && !isExpanded) {
      const strValue = JSON.stringify(value, null, 2);
      if (strValue.length > 100) {
        // Return plain text for truncated content instead of a JSON object
        return `Truncated ${strValue.length} characters...`;
      }
    }

    return value;
  };

  // Process entries based on expanded state
  const processEntries = () => {
    if (Array.isArray(interrupt)) {
      return isExpanded ? interrupt : interrupt.slice(0, 5);
    } else {
      const entries = Object.entries(interrupt);
      if (!isExpanded && shouldTruncate) {
        // When collapsed, process each value to potentially truncate it
        return entries.map(([key, value]) => [key, truncateValue(value)]);
      }
      return entries;
    }
  };

  const displayEntries = processEntries();

  return (
    <div className="overflow-hidden rounded-2xl border border-oats-dark bg-oats-light/40 shadow-xs">
      <div className="border-b border-oats-dark bg-oats-dark/60 px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-xs text-charcoal">Human Interrupt</h3>
        </div>
      </div>
      <motion.div
        className="min-w-full bg-oats/30"
        initial={false}
        animate={{ height: "auto" }}
        transition={{ duration: 0.3 }}
      >
        <div className="p-3">
          <AnimatePresence
            mode="wait"
            initial={false}
          >
            <motion.div
              key={isExpanded ? "expanded" : "collapsed"}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.2 }}
              style={{
                maxHeight: isExpanded ? "none" : "500px",
                overflow: "auto",
              }}
            >
              <table className="min-w-full table-fixed border-collapse border border-oats-dark/80 rounded-xl overflow-hidden shadow-2xs">
                <tbody className="divide-y divide-oats-dark/80">
                  {displayEntries.map((item, argIdx) => {
                    const [key, value] = Array.isArray(interrupt)
                      ? [argIdx.toString(), item]
                      : (item as [string, any]);
                    return (
                      <tr key={argIdx} className="hover:bg-oats/40 transition-colors">
                        <td className="w-1/3 border-r border-oats-dark/80 px-4 py-2.5 text-xs font-semibold text-charcoal/90 bg-oats-dark/20 whitespace-nowrap overflow-hidden text-ellipsis">
                          {key}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-charcoal-light break-words font-sans">
                          {renderInterruptStateItem(value)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </motion.div>
          </AnimatePresence>
        </div>
        {(shouldTruncate ||
          (Array.isArray(interrupt) && interrupt.length > 5)) && (
          <motion.button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex w-full cursor-pointer items-center justify-center gap-1 border-t border-oats-dark/80 py-2.5 text-xs font-semibold text-charcoal-light transition-all duration-200 ease-in-out bg-oats hover:bg-oats-dark hover:text-charcoal"
            initial={{ scale: 1 }}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
          >
            <span>{isExpanded ? "收起" : "展开全部"}</span>
            {isExpanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </motion.button>
        )}
      </motion.div>
    </div>
  );
}
