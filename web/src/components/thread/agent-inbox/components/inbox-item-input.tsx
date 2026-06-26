import React from "react";
import { DecisionWithEdits, SubmitType, HITLRequest } from "../types";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Undo2 } from "lucide-react";
import { MarkdownText } from "../../markdown-text";
import { haveArgsChanged } from "../utils";
import { fieldLabel } from "@/lib/tool-render";
import { toast } from "sonner";

function ResetButton({ handleReset }: { handleReset: () => void }) {
  return (
    <Button
      onClick={handleReset}
      variant="ghost"
      className="flex items-center justify-center gap-2 text-gray-500 hover:text-red-500"
    >
      <Undo2 className="h-4 w-4" />
      <span>重置</span>
    </Button>
  );
}

function isNoteArray(value: unknown): value is Record<string, unknown>[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(
      (x) =>
        x != null &&
        typeof x === "object" &&
        ("title" in x || "note_url" in x || "note_id" in x),
    )
  );
}

/** 笔记数组(如 adopt 的 notes)友好摘要,避免 HITL 弹窗里堆裸 JSON。 */
function NoteListSummary({ notes }: { notes: Record<string, unknown>[] }) {
  return (
    <div className="flex w-full flex-col gap-1.5 rounded-xl bg-zinc-100 p-3">
      <p className="text-[13px] font-semibold text-black">共 {notes.length} 篇笔记</p>
      <ul className="flex flex-col gap-1">
        {notes.slice(0, 8).map((n, i) => {
          const title = String(n.title ?? n.note_id ?? "(无标题)");
          const author = n.author ? `@${String(n.author)}` : "";
          const inter = n.interactive ?? n.likes;
          return (
            <li key={i} className="flex items-center gap-2 text-[12px] text-gray-700">
              <span className="text-coral">{i + 1}.</span>
              <span className="line-clamp-1 flex-1">{title}</span>
              {author && <span className="shrink-0 text-gray-400">{author}</span>}
              {inter != null && <span className="shrink-0 text-gray-400">🔥{String(inter)}</span>}
            </li>
          );
        })}
        {notes.length > 8 && (
          <li className="text-[12px] text-gray-400">…还有 {notes.length - 8} 篇</li>
        )}
      </ul>
    </div>
  );
}

function ArgsRenderer({ args }: { args: Record<string, unknown> }) {
  return (
    <div className="flex w-full flex-col items-start gap-6">
      {Object.entries(args).map(([key, value]) => {
        const stringValue =
          typeof value === "string" || typeof value === "number"
            ? value.toString()
            : JSON.stringify(value, null);

        return (
          <div
            key={`args-${key}`}
            className="flex flex-col items-start gap-1"
          >
            <p className="text-sm leading-[18px] text-wrap text-gray-600">
              {fieldLabel(key)}
            </p>
            {isNoteArray(value) ? (
              <NoteListSummary notes={value} />
            ) : (
              <span className="w-full max-w-full rounded-xl bg-zinc-100 p-3 text-[13px] leading-[18px] text-black">
                <MarkdownText>{stringValue}</MarkdownText>
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface InboxItemInputProps {
  interruptValue: HITLRequest;
  humanResponse: DecisionWithEdits[];
  supportsMultipleMethods: boolean;
  approveAllowed: boolean;
  hasEdited: boolean;
  hasAddedResponse: boolean;
  initialValues: Record<string, string>;
  isLoading: boolean;
  selectedSubmitType: SubmitType | undefined;

  setHumanResponse: React.Dispatch<React.SetStateAction<DecisionWithEdits[]>>;
  setSelectedSubmitType: React.Dispatch<
    React.SetStateAction<SubmitType | undefined>
  >;
  setHasAddedResponse: React.Dispatch<React.SetStateAction<boolean>>;
  setHasEdited: React.Dispatch<React.SetStateAction<boolean>>;

  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void> | void;
}

function ApproveOnly({
  isLoading,
  actionRequestArgs,
  handleSubmit,
}: {
  isLoading: boolean;
  actionRequestArgs: Record<string, unknown>;
  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void> | void;
}) {
  return (
    <div className="flex w-full flex-col items-start gap-4 rounded-lg border border-gray-300 p-6">
      {Object.keys(actionRequestArgs).length > 0 && (
        <ArgsRenderer args={actionRequestArgs} />
      )}
      <Button
        variant="brand"
        disabled={isLoading}
        onClick={handleSubmit}
        className="w-full"
      >
        批准执行
      </Button>
    </div>
  );
}

function EditActionCard({
  humanResponse,
  isLoading,
  initialValues,
  onEditChange,
  handleSubmit,
  actionArgs,
}: {
  humanResponse: DecisionWithEdits[];
  isLoading: boolean;
  initialValues: Record<string, string>;
  actionArgs: Record<string, unknown>;
  onEditChange: (
    text: string | string[],
    response: DecisionWithEdits,
    key: string | string[],
  ) => void;
  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void> | void;
}) {
  const defaultRows = React.useRef<Record<string, number>>({});
  const editResponse = humanResponse.find(
    (response) => response.type === "edit",
  );
  const approveResponse = humanResponse.find(
    (response) => response.type === "approve",
  );

  if (
    !editResponse ||
    editResponse.type !== "edit" ||
    typeof editResponse.edited_action !== "object" ||
    !editResponse.edited_action
  ) {
    if (approveResponse) {
      return (
        <ApproveOnly
          actionRequestArgs={actionArgs}
          isLoading={isLoading}
          handleSubmit={handleSubmit}
        />
      );
    }
    return null;
  }

  const header = editResponse.acceptAllowed ? "编辑 / 批准" : "编辑";
  const buttonText =
    editResponse.acceptAllowed && !editResponse.editsMade
      ? "批准执行"
      : "提交修改";

  const handleReset = () => {
    if (!editResponse.edited_action?.args) {
      return;
    }

    const keysToReset: string[] = [];
    const valuesToReset: string[] = [];
    Object.entries(initialValues).forEach(([key, value]) => {
      if (key in editResponse.edited_action.args) {
        const stringValue =
          typeof value === "string" || typeof value === "number"
            ? value.toString()
            : JSON.stringify(value, null);
        keysToReset.push(key);
        valuesToReset.push(stringValue);
      }
    });

    if (keysToReset.length > 0 && valuesToReset.length > 0) {
      onEditChange(valuesToReset, editResponse, keysToReset);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  return (
    <div className="flex w-full min-w-full flex-col items-start gap-4 rounded-lg border border-gray-300 p-6">
      <div className="flex w-full items-center justify-between">
        <p className="text-base font-semibold text-black">{header}</p>
        <ResetButton handleReset={handleReset} />
      </div>

      {Object.entries(editResponse.edited_action.args).map(
        ([key, value], idx) => {
          // 笔记数组(如 adopt 的 notes):只读友好摘要,不暴露裸 JSON / 不可逐字编辑
          if (isNoteArray(value)) {
            return (
              <div
                className="flex h-full w-full flex-col items-start gap-[6px] px-[1px]"
                key={`allow-edit-args--${key}-${idx}`}
              >
                <p className="min-w-fit text-sm font-medium">
                  {prettifyText(key)}
                </p>
                <NoteListSummary notes={value} />
              </div>
            );
          }

          const stringValue =
            typeof value === "string" || typeof value === "number"
              ? value.toString()
              : JSON.stringify(value, null);

          if (defaultRows.current[key] === undefined) {
            defaultRows.current[key] = !stringValue.length
              ? 3
              : Math.max(stringValue.length / 30, 7);
          }

          return (
            <div
              className="flex h-full w-full flex-col items-start gap-1 px-[1px]"
              key={`allow-edit-args--${key}-${idx}`}
            >
              <div className="flex w-full flex-col items-start gap-[6px]">
                <p className="min-w-fit text-sm font-medium">
                  {fieldLabel(key)}
                </p>
                <Textarea
                  disabled={isLoading}
                  className="h-full w-full max-w-full"
                  value={stringValue}
                  onChange={(event) =>
                    onEditChange(event.target.value, editResponse, key)
                  }
                  onKeyDown={handleKeyDown}
                  rows={defaultRows.current[key] || 8}
                />
              </div>
            </div>
          );
        },
      )}

      <div className="flex w-full items-center justify-end gap-2">
        <Button
          variant="brand"
          disabled={isLoading}
          onClick={handleSubmit}
        >
          {buttonText}
        </Button>
      </div>
    </div>
  );
}
const EditAndApprove = React.memo(EditActionCard);

function RejectActionCard({
  humanResponse,
  isLoading,
  onChange,
  handleSubmit,
  showArgs,
  actionArgs,
}: {
  humanResponse: DecisionWithEdits[];
  isLoading: boolean;
  onChange: (value: string, response: DecisionWithEdits) => void;
  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void> | void;
  showArgs: boolean;
  actionArgs: Record<string, unknown>;
}) {
  const rejectResponse = humanResponse.find(
    (response) => response.type === "reject",
  );

  if (!rejectResponse) {
    return null;
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  return (
    <div className="flex w-full max-w-full flex-col items-start gap-4 rounded-xl border border-gray-300 p-6">
      <div className="flex w-full items-center justify-between">
        <p className="text-base font-semibold text-black">驳回</p>
        <ResetButton handleReset={() => onChange("", rejectResponse)} />
      </div>

      {showArgs && <ArgsRenderer args={actionArgs} />}

      <div className="flex w-full flex-col items-start gap-[6px]">
        <p className="min-w-fit text-sm font-medium">驳回原因</p>
        <Textarea
          disabled={isLoading}
          className="w-full max-w-full"
          value={rejectResponse.message ?? ""}
          onChange={(event) => onChange(event.target.value, rejectResponse)}
          onKeyDown={handleKeyDown}
          rows={4}
          placeholder="告诉 AI 为什么驳回,它会据此调整..."
        />
      </div>

      <div className="flex w-full items-center justify-end gap-2">
        <Button
          variant="brand"
          disabled={isLoading}
          onClick={handleSubmit}
        >
          提交驳回
        </Button>
      </div>
    </div>
  );
}
const RejectCard = React.memo(RejectActionCard);

export function InboxItemInput({
  interruptValue,
  humanResponse,
  approveAllowed,
  hasEdited,
  hasAddedResponse,
  initialValues,
  isLoading,
  supportsMultipleMethods,
  selectedSubmitType,
  setHumanResponse,
  setSelectedSubmitType,
  setHasAddedResponse,
  setHasEdited,
  handleSubmit,
}: InboxItemInputProps) {
  const allowedDecisions =
    interruptValue.review_configs?.[0]?.allowed_decisions ?? [];
  const actionRequest = interruptValue.action_requests?.[0];
  const actionArgs = actionRequest?.args ?? {};
  const isEditAllowed = allowedDecisions.includes("edit");
  const isRejectAllowed = allowedDecisions.includes("reject");
  const hasArgs = Object.keys(actionArgs).length > 0;
  const showArgsInReject =
    hasArgs && !isEditAllowed && !approveAllowed && isRejectAllowed;
  const showArgsOutsideCards =
    hasArgs && !showArgsInReject && !isEditAllowed && !approveAllowed;

  const onEditChange = (
    change: string | string[],
    response: DecisionWithEdits,
    key: string | string[],
  ) => {
    if (
      (Array.isArray(change) && !Array.isArray(key)) ||
      (!Array.isArray(change) && Array.isArray(key))
    ) {
      toast.error("Error", {
        description: "Unable to update edited values.",
        richColors: true,
        closeButton: true,
      });
      return;
    }

    let valuesChanged = true;
    if (response.type === "edit" && response.edited_action) {
      const updatedArgs = { ...(response.edited_action.args || {}) };

      if (Array.isArray(change) && Array.isArray(key)) {
        change.forEach((value, index) => {
          if (index < key.length) {
            updatedArgs[key[index]] = value;
          }
        });
      } else {
        updatedArgs[key as string] = change as string;
      }

      valuesChanged = haveArgsChanged(updatedArgs, initialValues);
    }

    if (!valuesChanged) {
      setHasEdited(false);
      if (approveAllowed) {
        setSelectedSubmitType("approve");
      } else if (hasAddedResponse) {
        setSelectedSubmitType("reject");
      }
    } else {
      setSelectedSubmitType("edit");
      setHasEdited(true);
    }

    setHumanResponse((prev) => {
      if (response.type !== "edit" || !response.edited_action) {
        console.error("Mismatched response type for edit", response.type);
        return prev;
      }

      const newArgs =
        Array.isArray(change) && Array.isArray(key)
          ? {
              ...response.edited_action.args,
              ...Object.fromEntries(key.map((k, index) => [k, change[index]])),
            }
          : {
              ...response.edited_action.args,
              [key as string]: change as string,
            };

      const newEdit: DecisionWithEdits = {
        type: "edit",
        edited_action: {
          name: response.edited_action.name,
          args: newArgs,
        },
      };

      return prev.map((existing) => {
        if (existing.type !== "edit") {
          return existing;
        }

        if (existing.acceptAllowed) {
          return {
            ...newEdit,
            acceptAllowed: true,
            editsMade: valuesChanged,
          };
        }

        return newEdit;
      });
    });
  };

  const onRejectChange = (change: string, response: DecisionWithEdits) => {
    if (response.type !== "reject") {
      console.error("Mismatched response type for rejection");
      return;
    }

    const trimmed = change.trim();
    setHasAddedResponse(!!trimmed);

    if (!trimmed) {
      if (hasEdited) {
        setSelectedSubmitType("edit");
      } else if (approveAllowed) {
        setSelectedSubmitType("approve");
      }
    } else {
      setSelectedSubmitType("reject");
    }

    setHumanResponse((prev) =>
      prev.map((existing) =>
        existing.type === "reject"
          ? { type: "reject", message: change }
          : existing,
      ),
    );
  };

  return (
    <div className="flex w-full max-w-full flex-col items-start justify-start gap-2">
      {showArgsOutsideCards && <ArgsRenderer args={actionArgs} />}

      <div className="flex w-full flex-col items-stretch gap-2">
        <EditAndApprove
          humanResponse={humanResponse}
          isLoading={isLoading}
          initialValues={initialValues}
          actionArgs={actionArgs}
          onEditChange={onEditChange}
          handleSubmit={handleSubmit}
        />

        {supportsMultipleMethods ? (
          <div className="mx-auto mt-3 flex items-center gap-3">
            <Separator className="w-full" />
            <p className="text-sm text-gray-500">或</p>
            <Separator className="w-full" />
          </div>
        ) : null}

        <RejectCard
          humanResponse={humanResponse}
          isLoading={isLoading}
          showArgs={showArgsInReject}
          actionArgs={actionArgs}
          onChange={onRejectChange}
          handleSubmit={handleSubmit}
        />

        {isLoading && (
          <p className="text-sm text-gray-600">正在提交决定...</p>
        )}
        {selectedSubmitType && supportsMultipleMethods && (
          <p className="text-xs text-gray-500">
            当前选择:{
              selectedSubmitType === "approve"
                ? "批准执行"
                : selectedSubmitType === "reject"
                  ? "驳回"
                  : "编辑"
            }
          </p>
        )}
      </div>
    </div>
  );
}
