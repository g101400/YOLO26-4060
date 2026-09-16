package ncnn.v5lite.demo;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.util.AttributeSet;
import android.view.View;

/**
 * 检测结果绘制层：覆盖在 SurfaceView 之上，用 Android Canvas 画检测框与<b>中文</b>标签。
 *
 * 坐标为归一化值（0~1，相对于相机预览图像），因此不受预览分辨率/旋转/拉伸影响，
 * 只要本 View 与 SurfaceView 边界一致即可对齐。
 */
public class OverlayView extends View
{
    private float[] rects = new float[0];   // 每目标 4 个：x0,y0,x1,y1（归一化）
    private float[] probs = new float[0];
    private int[] labels = new int[0];

    private final Paint boxPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint tagPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);

    private static final int[] COLORS = {
            0xFFF44336, 0xFFE91E63, 0xFF9C27B0, 0xFF673AB7,
            0xFF3F51B5, 0xFF2196F3, 0xFF03A9F4, 0xFF00BCD4,
            0xFF009688, 0xFF4CAF50, 0xFF8BC34A, 0xFFCDDC39,
            0xFFFFC107, 0xFFFF9800, 0xFFFF5722, 0xFF795548
    };

    public OverlayView(Context context, AttributeSet attrs)
    {
        super(context, attrs);
        init();
    }

    public OverlayView(Context context)
    {
        super(context);
        init();
    }

    private void init()
    {
        float density = getResources().getDisplayMetrics().density;
        boxPaint.setStyle(Paint.Style.STROKE);
        boxPaint.setStrokeWidth(2.5f * density);
        tagPaint.setStyle(Paint.Style.FILL);
        textPaint.setColor(Color.WHITE);
        textPaint.setTextSize(14f * getResources().getDisplayMetrics().scaledDensity);
        textPaint.setTypeface(Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD));
        textPaint.setShadowLayer(3f, 0f, 1f, 0xAA000000);
    }

    /** 由相机线程经 Activity 转发调用（已在 UI 线程）。 */
    public void setResults(float[] r, float[] p, int[] l)
    {
        this.rects = (r == null) ? new float[0] : r;
        this.probs = (p == null) ? new float[0] : p;
        this.labels = (l == null) ? new int[0] : l;
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas)
    {
        super.onDraw(canvas);

        int w = getWidth();
        int h = getHeight();
        if (w == 0 || h == 0) return;

        int n = labels.length;
        if (n * 4 > rects.length) n = rects.length / 4;   // 防御：数组长度不匹配时不越界

        for (int i = 0; i < n; i++)
        {
            float x0 = rects[i * 4 + 0] * w;
            float y0 = rects[i * 4 + 1] * h;
            float x1 = rects[i * 4 + 2] * w;
            float y1 = rects[i * 4 + 3] * h;

            int color = COLORS[Math.abs(labels[i]) % COLORS.length];
            boxPaint.setColor(color);
            tagPaint.setColor(color);

            canvas.drawRect(x0, y0, x1, y1, boxPaint);

            String text = CocoLabels.cn(labels[i]) + " " + Math.round(probs[i] * 100) + "%";
            Paint.FontMetrics fm = textPaint.getFontMetrics();
            float textH = fm.bottom - fm.top;
            float textW = textPaint.measureText(text);

            float baseY = y0 - 6f;                       // 标签基线（框上方）
            if (baseY - textH < 0f) baseY = y0 + textH;  // 顶部越界则改画在框内
            float tagLeft = Math.min(x0, w - textW - 10f);
            tagLeft = Math.max(0f, tagLeft);

            canvas.drawRect(tagLeft, baseY - textH, tagLeft + textW + 10f, baseY + 4f, tagPaint);
            canvas.drawText(text, tagLeft + 5f, baseY, textPaint);
        }
    }
}
