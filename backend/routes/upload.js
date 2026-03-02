import multer from 'multer';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const UPLOAD_DIR = path.join(__dirname, '../uploads');

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, UPLOAD_DIR),
  filename: (req, file, cb) => cb(null, `bg_${Date.now()}${path.extname(file.originalname)}`),
});

const upload = multer({
  storage,
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    // 严格检查 MIME 类型和扩展名
    const allowedMimes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    const allowedExts = ['.jpg', '.jpeg', '.png', '.webp', '.gif'];
    const ext = path.extname(file.originalname).toLowerCase();
    
    if (!allowedMimes.includes(file.mimetype) || !allowedExts.includes(ext)) {
      cb(new Error('只支持 jpg/png/webp/gif 图片文件'));
    } else {
      cb(null, true);
    }
  },
});

export { upload };

export async function uploadBackground(req, res) {
  if (!req.file) return res.status(400).json({ error: '未收到文件' });
  res.json({ success: true, url: `/xhs/uploads/${req.file.filename}` });
}
