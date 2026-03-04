// ==========================================
// VidFetch — منطق الواجهة الأمامية
// ==========================================

const $ = (sel) => document.querySelector(sel);

// عناصر الواجهة
const urlInput     = $("#urlInput");
const pasteBtn     = $("#pasteBtn");
const fetchBtn     = $("#fetchBtn");
const btnLoader    = $("#btnLoader");
const inputHint    = $("#inputHint");
const resultCard   = $("#resultCard");
const videoThumb   = $("#videoThumb");
const videoTitle   = $("#videoTitle");
const streamBtn    = $("#streamBtn");
const downloadBtn  = $("#downloadBtn");
const playerSection= $("#playerSection");
const videoPlayer  = $("#videoPlayer");
const errorToast   = $("#errorToast");
const errorMessage = $("#errorMessage");

// متغير لتخزين بيانات الفيديو الحالية
let currentVideo = null;

// ==========================================
// التحقق من الرابط
// ==========================================
function isValidUrl(str) {
    try {
        const url = new URL(str);
        return url.protocol === "http:" || url.protocol === "https:";
    } catch {
        return false;
    }
}

// ==========================================
// إظهار / إخفاء رسالة الخطأ
// ==========================================
function showError(msg) {
    errorMessage.textContent = msg;
    errorToast.classList.add("visible");
    setTimeout(() => {
        errorToast.classList.remove("visible");
    }, 5000);
}

function setHint(msg) {
    inputHint.textContent = msg;
}

function clearHint() {
    inputHint.textContent = "";
}

// ==========================================
// حالة التحميل (Loading)
// ==========================================
function setLoading(state) {
    if (state) {
        fetchBtn.classList.add("loading");
        fetchBtn.disabled = true;
    } else {
        fetchBtn.classList.remove("loading");
        fetchBtn.disabled = false;
    }
}

// ==========================================
// جلب الفيديو من السيرفر
// ==========================================
async function fetchVideo() {
    const url = urlInput.value.trim();

    // التحقق من الإدخال قبل الإرسال
    if (!url) {
        setHint("الرجاء إدخال رابط الفيديو");
        return;
    }

    if (!isValidUrl(url)) {
        setHint("الرابط غير صحيح — تأكد أنه يبدأ بـ https://");
        return;
    }

    clearHint();
    setLoading(true);

    // إخفاء النتيجة السابقة
    resultCard.classList.remove("visible");
    playerSection.classList.remove("visible");
    videoPlayer.pause();
    videoPlayer.removeAttribute("src");

    try {
        const res = await fetch("/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: url }),
        });

        const data = await res.json();

        if (!res.ok) {
            showError(data.error || "حدث خطأ غير متوقع.");
            return;
        }

        // حفظ البيانات وعرض البطاقة
        currentVideo = data;
        videoThumb.src = data.thumbnail || "";
        videoTitle.textContent = data.title || "بدون عنوان";
        downloadBtn.href = data.download_url_high || data.stream_url;

        resultCard.classList.add("visible");

    } catch (err) {
        console.error("Fetch error:", err);
        showError("تعذر الاتصال بالسيرفر. تأكد من اتصالك بالإنترنت.");
    } finally {
        setLoading(false);
    }
}

// ==========================================
// تشغيل الفيديو مباشرة
// ==========================================
function playStream() {
    if (!currentVideo || !currentVideo.stream_url) return;

    playerSection.classList.add("visible");
    videoPlayer.src = currentVideo.stream_url;
    videoPlayer.play().catch(() => {});

    // التمرير لمشغل الفيديو
    playerSection.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ==========================================
// ربط الأحداث (Event Listeners)
// ==========================================

// زر الجلب
fetchBtn.addEventListener("click", fetchVideo);

// Enter في حقل الإدخال
urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") fetchVideo();
});

// تنظيف التنبيه عند الكتابة
urlInput.addEventListener("input", clearHint);

// زر اللصق من الحافظة
pasteBtn.addEventListener("click", async () => {
    try {
        const text = await navigator.clipboard.readText();
        if (text) {
            urlInput.value = text;
            urlInput.focus();
            clearHint();
        }
    } catch {
        // المتصفح لا يدعم اللصق — يتجاهل بصمت
    }
});

// زر التشغيل المباشر
streamBtn.addEventListener("click", playStream);

// النقر على الصورة المصغرة = تشغيل
videoThumb.addEventListener("click", playStream);
