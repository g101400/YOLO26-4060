package ncnn.v5lite.demo;

import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * 检测结果自动落盘：每条 = 时间,物体,置信度（CSV）。
 *
 * 2026-09-16 改动（按需求「存到公共 Downloads + 按天保留历史」）：
 *   - 存储位置：公共「下载」目录 Downloads/YOLOv26-Lite检测记录/detect_yyyyMMdd.csv，
 *     用户用文件管理器直接可见、可拷走，卸载应用不会丢失。
 *   - 按天分文件：每天一份 csv，历史长期保留，不做自动清理。
 *   - 双通道实现：
 *       Android 10(API 29)+ → MediaStore.Downloads（分区存储，免权限）
 *       Android 9 及以下    → Environment.getExternalStoragePublicDirectory(DIRECTORY_DOWNLOADS)
 *                             （需 WRITE_EXTERNAL_STORAGE，manifest 里 maxSdkVersion=28）
 *   - 首行写 UTF-8 BOM + 表头，Excel 直接打开中文不乱码。
 */
public class DetectLog
{
    /** 公共下载目录下的子目录名 */
    public static final String SUB_DIR = "YOLOv26-Lite检测记录";
    private static final String HEADER = "时间,物体,置信度\n";
    private static final String MIME = "text/csv";
    private static final String PREFIX = "detect_";
    private static final String SUFFIX = ".csv";

    private final Context ctx;
    private final ContentResolver resolver;

    private String day;      // 当前归档日 yyyyMMdd（跨天自动切换新文件）
    private Uri dayUri;      // API 29+ 的 MediaStore 句柄
    private File dayFile;    // API ≤28 的公共目录文件

    /** 历史条目：文件名 + 记录条数 */
    public static class Item
    {
        public final String name;
        public final int rows;

        public Item(String name, int rows)
        {
            this.name = name;
            this.rows = rows;
        }

        /** detect_20260916.csv → 2026-09-16 */
        public String prettyDate()
        {
            String d = name;
            if (d.startsWith(PREFIX)) d = d.substring(PREFIX.length());
            if (d.endsWith(SUFFIX)) d = d.substring(0, d.length() - SUFFIX.length());
            if (d.length() == 8)
            {
                return d.substring(0, 4) + "-" + d.substring(4, 6) + "-" + d.substring(6, 8);
            }
            return d;
        }
    }

    public DetectLog(Context ctx)
    {
        this.ctx = ctx.getApplicationContext();
        this.resolver = this.ctx.getContentResolver();
        resolveDay(true);
    }

    /* ---------------- 每日文件解析 ---------------- */

    private static String today()
    {
        return new SimpleDateFormat("yyyyMMdd", Locale.CHINA).format(new Date());
    }

    private synchronized void resolveDay(boolean createIfMissing)
    {
        day = today();
        dayUri = null;
        dayFile = null;

        if (Build.VERSION.SDK_INT >= 29)
        {
            dayUri = findExisting(dayFileName());
            if (dayUri == null && createIfMissing)
            {
                dayUri = createViaMediaStore(dayFileName());
            }
            if (dayUri == null)
            {
                dayFile = ensureLegacy(dayFileName());   // 兜底：MediaStore 不可用时走旧式公共目录
            }
        }
        else
        {
            dayFile = ensureLegacy(dayFileName());
        }
    }

    private String dayFileName()
    {
        return PREFIX + day + SUFFIX;
    }

    private String relativePath()
    {
        return Environment.DIRECTORY_DOWNLOADS + "/" + SUB_DIR;
    }

    /** API 29+：查找当天已存在的记录文件 */
    private Uri findExisting(String fileName)
    {
        Uri ext = MediaStore.Downloads.EXTERNAL_CONTENT_URI;
        String[] proj = new String[] {
                MediaStore.MediaColumns._ID,
                MediaStore.MediaColumns.DISPLAY_NAME,
                MediaStore.MediaColumns.RELATIVE_PATH
        };
        Cursor cur = null;
        try
        {
            cur = resolver.query(ext, proj, MediaStore.MediaColumns.DISPLAY_NAME + "=?",
                    new String[] {fileName}, null);
            if (cur != null)
            {
                while (cur.moveToNext())
                {
                    String rp = cur.getString(2);
                    if (rp == null || rp.contains(SUB_DIR))     // 避免同名但位于别处的文件
                    {
                        return ContentUris.withAppendedId(ext, cur.getLong(0));
                    }
                }
            }
        }
        catch (Exception e)
        {
            // 忽略：个别 ROM 的 MediaStore 行为异常，交由兜底路径处理
        }
        finally
        {
            if (cur != null) cur.close();
        }
        return null;
    }

    /** API 29+：在公共 Downloads 下新建当天文件并写表头 */
    private Uri createViaMediaStore(String fileName)
    {
        try
        {
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            cv.put(MediaStore.MediaColumns.MIME_TYPE, MIME);
            cv.put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath());
            Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (uri != null)
            {
                writeRaw(uri, null, "\ufeff" + HEADER, false);
            }
            return uri;
        }
        catch (Exception e)
        {
            return null;
        }
    }

    /** API ≤28（及兜底）：直接操作公共下载目录 */
    private File ensureLegacy(String fileName)
    {
        try
        {
            File dir = new File(Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DOWNLOADS), SUB_DIR);
            if (!dir.exists()) dir.mkdirs();
            File f = new File(dir, fileName);
            if (!f.exists())
            {
                writeRaw(null, f, "\ufeff" + HEADER, false);
            }
            return f;
        }
        catch (Exception e)
        {
            return null;
        }
    }

    /* ---------------- 写入 ---------------- */

    public synchronized boolean append(String time, String name, float prob)
    {
        String line = time + "," + name + "," + String.format(Locale.US, "%.2f", prob) + "\n";
        if (!today().equals(day)) resolveDay(true);     // 跨天：自动切到新文件，历史文件保留
        return writeRaw(dayUri, dayFile, line, true);
    }

    public synchronized void clearToday()
    {
        writeRaw(dayUri, dayFile, "\ufeff" + HEADER, false);
    }

    private boolean writeRaw(Uri uri, File file, String content, boolean append)
    {
        try
        {
            OutputStream os;
            if (uri != null)
            {
                os = resolver.openOutputStream(uri, append ? "wa" : "w");
            }
            else if (file != null)
            {
                os = new FileOutputStream(file, append);
            }
            else
            {
                return false;
            }
            if (os == null) return false;
            OutputStreamWriter osw = new OutputStreamWriter(os, "UTF-8");
            osw.write(content);
            osw.flush();
            osw.close();
            return true;
        }
        catch (Exception e)
        {
            return false;
        }
    }

    /* ---------------- 读取 / 历史 ---------------- */

    /** 当天已记录条数（不含表头） */
    public int rowsToday()
    {
        if (!today().equals(day)) resolveDay(false);
        String txt = readRaw(dayUri, dayFile);
        return txt == null ? 0 : Math.max(0, countLines(txt) - 1);
    }

    /** 记录目录描述，用于界面展示 */
    public String location()
    {
        if (dayUri != null) return "下载/" + SUB_DIR;
        if (dayFile != null) return dayFile.getParent();
        return "不可用（存储未授权/未挂载）";
    }

    public String currentName()
    {
        return dayFileName();
    }

    /** 历史文件列表（按日期倒序，含条数） */
    public List<Item> history()
    {
        List<Item> out = new ArrayList<Item>();
        if (Build.VERSION.SDK_INT >= 29 && dayUri != null)
        {
            Uri ext = MediaStore.Downloads.EXTERNAL_CONTENT_URI;
            String[] proj = new String[] {
                    MediaStore.MediaColumns._ID,
                    MediaStore.MediaColumns.DISPLAY_NAME,
                    MediaStore.MediaColumns.RELATIVE_PATH
            };
            Cursor cur = null;
            try
            {
                cur = resolver.query(ext, proj, MediaStore.MediaColumns.DISPLAY_NAME + " LIKE ?",
                        new String[] {PREFIX + "%"}, null);
                if (cur != null)
                {
                    while (cur.moveToNext())
                    {
                        String name = cur.getString(1);
                        String rp = cur.getString(2);
                        if (name == null || !name.endsWith(SUFFIX)) continue;
                        if (rp != null && !rp.contains(SUB_DIR)) continue;
                        Uri u = ContentUris.withAppendedId(ext, cur.getLong(0));
                        String txt = readRaw(u, null);
                        out.add(new Item(name, txt == null ? 0 : Math.max(0, countLines(txt) - 1)));
                    }
                }
            }
            catch (Exception e)
            {
                // 查询失败时退回目录遍历
            }
            finally
            {
                if (cur != null) cur.close();
            }
        }
        if (out.isEmpty() && dayFile != null && dayFile.getParentFile() != null)
        {
            File[] fs = dayFile.getParentFile().listFiles();
            if (fs != null)
            {
                for (File f : fs)
                {
                    if (f.isFile() && f.getName().startsWith(PREFIX) && f.getName().endsWith(SUFFIX))
                    {
                        String txt = readRaw(null, f);
                        out.add(new Item(f.getName(), txt == null ? 0 : Math.max(0, countLines(txt) - 1)));
                    }
                }
            }
        }
        Collections.sort(out, new Comparator<Item>() {
            @Override
            public int compare(Item a, Item b)
            {
                return b.name.compareTo(a.name);      // 日期倒序
            }
        });
        return out;
    }

    /** 删除全部历史（含当天） */
    public synchronized int clearAll()
    {
        int n = 0;
        for (Item it : history())
        {
            if (deleteByName(it.name)) n++;
        }
        resolveDay(true);
        return n;
    }

    private boolean deleteByName(String name)
    {
        try
        {
            if (Build.VERSION.SDK_INT >= 29)
            {
                Uri ext = MediaStore.Downloads.EXTERNAL_CONTENT_URI;
                String[] proj = new String[] {
                        MediaStore.MediaColumns._ID,
                        MediaStore.MediaColumns.DISPLAY_NAME,
                        MediaStore.MediaColumns.RELATIVE_PATH
                };
                Cursor cur = resolver.query(ext, proj, MediaStore.MediaColumns.DISPLAY_NAME + "=?",
                        new String[] {name}, null);
                boolean done = false;
                if (cur != null)
                {
                    while (cur.moveToNext())
                    {
                        String rp = cur.getString(2);
                        if (rp != null && !rp.contains(SUB_DIR)) continue;
                        if (resolver.delete(ContentUris.withAppendedId(ext, cur.getLong(0)), null, null) > 0)
                        {
                            done = true;
                        }
                    }
                    cur.close();
                }
                if (done) return true;
            }
            if (dayFile != null && dayFile.getParentFile() != null)
            {
                File f = new File(dayFile.getParentFile(), name);
                if (f.exists()) return f.delete();
            }
        }
        catch (Exception e)
        {
            // 忽略
        }
        return false;
    }

    private String readRaw(Uri uri, File file)
    {
        InputStream is = null;
        try
        {
            is = (uri != null) ? resolver.openInputStream(uri)
                               : (file != null && file.exists() ? new java.io.FileInputStream(file) : null);
            if (is == null) return null;
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = is.read(buf)) > 0) bos.write(buf, 0, n);
            return new String(bos.toByteArray(), "UTF-8");
        }
        catch (Exception e)
        {
            return null;
        }
        finally
        {
            if (is != null)
            {
                try { is.close(); } catch (Exception e) { }
            }
        }
    }

    private static int countLines(String s)
    {
        int c = 0;
        for (int i = 0; i < s.length(); i++)
        {
            if (s.charAt(i) == '\n') c++;
        }
        return c;
    }
}
