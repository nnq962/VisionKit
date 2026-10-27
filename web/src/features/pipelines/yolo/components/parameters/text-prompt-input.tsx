import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { commonTextPrompts, defaultTextPrompts, parseTextPrompts } from "../../text-prompts";

export function TextPromptInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const prompts = parseTextPrompts(value);
  function toggle(prompt: string) {
    const exists = prompts.some((item) => item.toLowerCase() === prompt);
    onChange((exists ? prompts.filter((item) => item.toLowerCase() !== prompt) : [...prompts, prompt]).join(", "));
  }
  return (
    <div className="space-y-3 border-t pt-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor="text-prompts">Vật thể cần nhận diện · YOLOE</Label>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => onChange(defaultTextPrompts)}>Dùng gợi ý</Button>
          <Button variant="ghost" size="sm" onClick={() => onChange("")}>Xoá hết</Button>
        </div>
      </div>
      <textarea id="text-prompts" value={value} onChange={(event) => onChange(event.target.value)} rows={4}
        aria-describedby="text-prompts-hint"
        className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        placeholder="person, car, laptop, cell phone" />
      <p id="text-prompts-hint" className="text-xs leading-5 text-muted-foreground">
        Nhập tên vật thể bằng tiếng Anh, cách nhau bằng dấu phẩy hoặc xuống dòng. Tối đa 80 vật thể; nhãn kết quả dùng tên đã nhập.
      </p>
      <div className="flex flex-wrap gap-2" aria-label="Vật thể thường gặp">
        {commonTextPrompts.map(([label, prompt]) => (
          <Button key={prompt} size="sm" variant={prompts.some((item) => item.toLowerCase() === prompt) ? "secondary" : "outline"}
            aria-pressed={prompts.some((item) => item.toLowerCase() === prompt)} title={prompt} onClick={() => toggle(prompt)}>{label}</Button>
        ))}
      </div>
    </div>
  );
}
