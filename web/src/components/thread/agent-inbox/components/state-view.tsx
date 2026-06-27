import { ChevronRight, X, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { useEffect, useState } from "react";
import {
  baseMessageObject,
  isArrayOfMessages,
  prettifyText,
  unknownToPrettyDate,
} from "../utils";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { BaseMessage } from "@langchain/core/messages";
import { ToolCall } from "@langchain/core/messages/tool";
import { ToolCallTable } from "./tool-call-table";
import { Button } from "@/components/ui/button";
import { MarkdownText } from "../../markdown-text";

interface StateViewRecursiveProps {
  value: unknown;
  expanded?: boolean;
}

const messageTypeToLabel = (message: BaseMessage) => {
  let type = "";
  if ("type" in message) {
    type = message.type as string;
  } else if ("getType" in message) {
    type = (message as BaseMessage).getType();
  }

  switch (type) {
    case "human":
      return "User";
    case "ai":
      return "Assistant";
    case "tool":
      return "Tool";
    case "System":
      return "System";
    default:
      return "";
  }
};

function tryParseJson(val: unknown): unknown {
  if (typeof val !== "string") return null;
  const trimmed = val.trim();
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return null;
    }
  }
  return null;
}

function PrettyJsonRenderer({ value }: { value: unknown }) {
  if (value == null) return null;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-gray-400">Empty list</span>;
    return (
      <ul className="flex flex-col gap-2.5 w-full pl-2">
        {value.map((item, idx) => (
          <li
            key={idx}
            className="flex flex-col gap-1.5 rounded-xl border border-border bg-oats-light/40 p-3 text-sm shadow-2xs"
          >
            {typeof item === "object" ? (
              <PrettyJsonRenderer value={item} />
            ) : (
              <MarkdownText>{String(item)}</MarkdownText>
            )}
          </li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-gray-400">Empty object</span>;
    return (
      <div className="flex flex-col gap-3 w-full">
        {entries.map(([key, val], idx) => {
          const formattedKey = key
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase());
          return (
            <div
              key={idx}
              className="flex flex-col gap-1 border-b border-gray-100 pb-2.5 last:border-0 last:pb-0"
            >
              <span className="text-xs font-semibold text-gray-500 tracking-wider uppercase">
                {formattedKey}
              </span>
              <div className="text-sm text-charcoal-dark pl-1">
                {typeof val === "object" && val !== null ? (
                  <div className="mt-1.5 rounded-xl border border-border bg-oats-light/20 p-3">
                    <PrettyJsonRenderer value={val} />
                  </div>
                ) : (
                  <MarkdownText>{String(val)}</MarkdownText>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return <MarkdownText>{String(value)}</MarkdownText>;
}

function MessagesRenderer({ messages }: { messages: BaseMessage[] }) {
  return (
    <div className="flex w-full flex-col gap-4">
      {messages.map((msg, idx) => {
        const messageTypeLabel = messageTypeToLabel(msg);
        const content =
          typeof msg.content === "string"
            ? msg.content
            : JSON.stringify(msg.content, null);

        const parsedJson = typeof msg.content === "string" ? tryParseJson(msg.content) : (typeof msg.content === "object" && msg.content !== null ? msg.content : null);
        const isJson = parsedJson !== null && typeof parsedJson === "object";

        return (
          <div
            key={msg.id ?? `message-${idx}`}
            className="ml-2 flex w-full flex-col gap-2 rounded-xl border border-border/40 bg-oats-light/30 p-4 shadow-2xs"
          >
            <p className="font-semibold text-charcoal-dark text-sm border-b border-border pb-1.5 mb-1">{messageTypeLabel}</p>
            {content && (
              isJson ? (
                <div className="w-full my-1 rounded-xl border border-border bg-white p-4 shadow-2xs">
                  <PrettyJsonRenderer value={parsedJson} />
                </div>
              ) : (
                <MarkdownText>{content}</MarkdownText>
              )
            )}
            {"tool_calls" in msg && msg.tool_calls ? (
              <div className="flex w-full flex-col items-start gap-1">
                {(msg.tool_calls as ToolCall[]).map((tc, idx) => (
                  <ToolCallTable
                    key={tc.id ?? `tool-call-${idx}`}
                    toolCall={tc}
                  />
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function StateViewRecursive(props: StateViewRecursiveProps) {
  const date = unknownToPrettyDate(props.value);
  if (date) {
    return <p className="font-light text-gray-600">{date}</p>;
  }

  if (["string", "number"].includes(typeof props.value)) {
    const parsedJson = typeof props.value === "string" ? tryParseJson(props.value) : null;
    if (parsedJson !== null && typeof parsedJson === "object") {
      return (
        <div className="w-full my-1 rounded-xl border border-border bg-white p-4 shadow-2xs">
          <PrettyJsonRenderer value={parsedJson} />
        </div>
      );
    }
    return <MarkdownText>{props.value as string}</MarkdownText>;
  }

  if (typeof props.value === "boolean") {
    return <MarkdownText>{JSON.stringify(props.value)}</MarkdownText>;
  }

  if (props.value == null) {
    return <p className="font-light whitespace-pre-wrap text-gray-600">null</p>;
  }

  if (Array.isArray(props.value)) {
    if (props.value.length > 0 && isArrayOfMessages(props.value)) {
      return <MessagesRenderer messages={props.value} />;
    }

    const valueArray = props.value as unknown[];
    return (
      <div className="flex w-full flex-row items-start justify-start gap-1">
        <span className="font-normal text-black">[</span>
        {valueArray.map((item, idx) => {
          const itemRenderValue = baseMessageObject(item);
          return (
            <div
              key={`state-view-${idx}`}
              className="flex w-full flex-row items-start whitespace-pre-wrap"
            >
              <StateViewRecursive value={itemRenderValue} />
              {idx < valueArray?.length - 1 && (
                <span className="font-normal text-black">,&nbsp;</span>
              )}
            </div>
          );
        })}
        <span className="font-normal text-black">]</span>
      </div>
    );
  }

  if (typeof props.value === "object") {
    if (Object.keys(props.value).length === 0) {
      return <p className="font-light text-gray-600">{"{}"}</p>;
    }
    return (
      <div className="relative ml-6 flex w-full flex-col items-start justify-start gap-1">
        {/* Vertical line */}
        <div className="absolute top-0 left-[-24px] h-full w-[1px] bg-gray-200" />

        {Object.entries(props.value).map(([key, value], idx) => (
          <div
            key={`state-view-object-${key}-${idx}`}
            className="relative w-full"
          >
            {/* Horizontal connector line */}
            <div className="absolute top-[10px] left-[-20px] h-[1px] w-[18px] bg-gray-200" />
            <StateViewObject
              expanded={props.expanded}
              keyName={key}
              value={value}
            />
          </div>
        ))}
      </div>
    );
  }
}

function HasContentsEllipsis({ onClick }: { onClick?: () => void }) {
  return (
    <span
      onClick={onClick}
      className={cn(
        "rounded-md p-[2px] font-mono text-[10px] leading-3",
        "bg-gray-50 text-gray-600 hover:bg-gray-100 hover:text-gray-800",
        "cursor-pointer transition-colors ease-in-out",
        "inline-block -translate-y-[2px]",
      )}
    >
      {"{...}"}
    </span>
  );
}

interface StateViewProps {
  keyName: string;
  value: unknown;
  /**
   * Whether or not to expand or collapse the view
   * @default true
   */
  expanded?: boolean;
}

export function StateViewObject(props: StateViewProps) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (props.expanded != null) {
      setExpanded(props.expanded);
    }
  }, [props.expanded]);

  return (
    <div className="relative flex flex-row items-start justify-start gap-2 text-sm">
      <motion.div
        initial={false}
        animate={{ rotate: expanded ? 90 : 0 }}
        transition={{ duration: 0.2 }}
      >
        <div
          onClick={() => setExpanded((prev) => !prev)}
          className="flex h-5 w-5 cursor-pointer items-center justify-center rounded-md text-gray-500 transition-colors ease-in-out hover:bg-gray-100 hover:text-black"
        >
          <ChevronRight className="h-4 w-4" />
        </div>
      </motion.div>
      <div className="flex w-full flex-col items-start justify-start gap-1">
        <p className="font-normal text-black">
          {prettifyText(props.keyName)}{" "}
          {!expanded && (
            <HasContentsEllipsis onClick={() => setExpanded((prev) => !prev)} />
          )}
        </p>
        <motion.div
          initial={false}
          animate={{
            height: expanded ? "auto" : 0,
            opacity: expanded ? 1 : 0,
          }}
          transition={{
            duration: 0.2,
            ease: "easeInOut",
          }}
          style={{ overflow: "hidden" }}
          className="relative w-full"
        >
          <StateViewRecursive
            expanded={props.expanded}
            value={props.value}
          />
        </motion.div>
      </div>
    </div>
  );
}

interface StateViewComponentProps {
  values: Record<string, any>;
  description: string | undefined;
  handleShowSidePanel: (showState: boolean, showDescription: boolean) => void;
  view: "description" | "state";
}

export function StateView({
  handleShowSidePanel,
  view,
  values,
  description,
}: StateViewComponentProps) {
  const [expanded, setExpanded] = useState(false);

  if (!values) {
    return <div>No state found</div>;
  }

  return (
    <div
      className={cn(
        "flex min-w-full flex-row gap-0",
        view === "state" &&
          "border-t-[1px] border-gray-100 lg:border-t-[0px] lg:border-l-[1px]",
      )}
    >
      {view === "description" && (
        <div className="pt-6 pb-2">
          <MarkdownText>
            {description ?? "No description provided"}
          </MarkdownText>
        </div>
      )}
      {view === "state" && (
        <div className="flex flex-col items-start justify-start gap-1">
          {Object.entries(values).map(([k, v], idx) => (
            <StateViewObject
              expanded={expanded}
              key={`state-view-${k}-${idx}`}
              keyName={k}
              value={v}
            />
          ))}
        </div>
      )}
      <div className="flex items-start justify-end gap-2">
        {view === "state" && (
          <Button
            onClick={() => setExpanded((prev) => !prev)}
            variant="ghost"
            className="text-gray-600"
            size="sm"
          >
            {expanded ? (
              <ChevronsUpDown className="h-4 w-4" />
            ) : (
              <ChevronsDownUp className="h-4 w-4" />
            )}
          </Button>
        )}

        <Button
          onClick={() => handleShowSidePanel(false, false)}
          variant="ghost"
          className="text-gray-600"
          size="sm"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
