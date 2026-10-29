/** Nhãn gợi ý cho người dùng; giá trị tiếng Anh được gửi nguyên vẹn vào YOLOE. */
export const commonTextPrompts = [
  ["Người", "person"], ["Ô tô", "car"], ["Xe máy", "motorcycle"],
  ["Xe đạp", "bicycle"], ["Xe buýt", "bus"], ["Xe tải", "truck"],
  ["Laptop", "laptop"], ["Màn hình máy tính", "computer monitor"],
  ["Bàn phím", "keyboard"], ["Chuột máy tính", "computer mouse"],
  ["Điện thoại", "cell phone"], ["TV", "television"],
  ["Bàn", "table"], ["Ghế", "chair"], ["Sofa", "sofa"],
  ["Ba lô", "backpack"], ["Túi xách", "handbag"], ["Chai nước", "bottle"],
  ["Cốc", "cup"], ["Sách", "book"], ["Chó", "dog"], ["Mèo", "cat"],
] as const;

export const defaultTextPrompts = commonTextPrompts.map(([, prompt]) => prompt).join(", ");

export function parseTextPrompts(value: string): string[] {
  return value.split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
}

export function validateTextPrompts(value: string): string {
  const prompts = parseTextPrompts(value);
  if (!prompts.length) return "Nhập ít nhất một vật thể cần nhận diện.";
  if (prompts.length > 80) return "Dùng tối đa 80 vật thể cho một lượt chạy.";
  if (prompts.some((item) => item.length > 80 || /[\x00-\x1f\x7f]/.test(item)))
    return "Mỗi prompt tối đa 80 ký tự, không chứa ký tự điều khiển.";
  if (new Set(prompts.map((item) => item.toLowerCase())).size !== prompts.length)
    return "Danh sách vật thể không được trùng nhau.";
  return "";
}
