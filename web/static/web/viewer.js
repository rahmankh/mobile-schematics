(function () {
  'use strict';

  var PDFJS_WORKER =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  document.querySelectorAll('.schematic-viewer').forEach(initViewer);

  function harden(el) {
    el.addEventListener('contextmenu', function (event) {
      event.preventDefault();
    });
    el.addEventListener('dragstart', function (event) {
      event.preventDefault();
    });
    el.addEventListener('copy', function (event) {
      event.preventDefault();
    });
    el.addEventListener('selectstart', function (event) {
      event.preventDefault();
    });
  }

  function setStatus(root, message) {
    var status = root.querySelector('.schematic-viewer-status');
    if (status) {
      status.textContent = message;
    }
  }

  function tileWatermark(root) {
    var mark = root.querySelector('.schematic-viewer-watermark');
    if (!mark) {
      return;
    }
    var text = (mark.textContent || '').trim();
    if (!text) {
      return;
    }
    mark.textContent = '';
    for (var i = 0; i < 18; i += 1) {
      var span = document.createElement('span');
      span.textContent = text;
      mark.appendChild(span);
    }
  }

  function fitViewport(page, host) {
    var base = page.getViewport({ scale: 1 });
    var width = Math.max(host.clientWidth || 320, 280);
    var scale = width / base.width;
    return page.getViewport({ scale: Math.min(Math.max(scale, 0.6), 2.2) });
  }

  async function renderPdf(blob, host, root) {
    if (typeof window.pdfjsLib === 'undefined') {
      setStatus(root, 'نمایشگر PDF بارگذاری نشد.');
      return;
    }
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
    var buffer = await blob.arrayBuffer();
    var pdf = await window.pdfjsLib.getDocument({ data: buffer }).promise;
    host.replaceChildren();
    for (var pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      var page = await pdf.getPage(pageNumber);
      var viewport = fitViewport(page, host);
      var canvas = document.createElement('canvas');
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.setAttribute('aria-label', 'صفحه ' + pageNumber);
      var context = canvas.getContext('2d');
      await page.render({ canvasContext: context, viewport: viewport }).promise;
      host.appendChild(canvas);
    }
    setStatus(root, '');
  }

  function renderImage(blob, host, root) {
    var objectUrl = URL.createObjectURL(blob);
    var img = document.createElement('img');
    img.alt = root.dataset.title || 'بردویو';
    img.draggable = false;
    img.onload = function () {
      URL.revokeObjectURL(objectUrl);
    };
    img.src = objectUrl;
    host.replaceChildren(img);
    setStatus(root, '');
  }

  async function initViewer(root) {
    harden(root);
    tileWatermark(root);
    var host = root.querySelector('.schematic-viewer-canvas-host');
    var url = root.dataset.viewUrl;
    var kind = root.dataset.viewerKind;
    if (!host || !url) {
      return;
    }
    try {
      var response = await fetch(url, {
        credentials: 'same-origin',
        headers: { Accept: 'application/pdf,image/*,*/*' },
      });
      if (!response.ok) {
        setStatus(root, 'دسترسی به نمایشگر برقرار نشد.');
        return;
      }
      var blob = await response.blob();
      if (kind === 'pdf') {
        await renderPdf(blob, host, root);
        return;
      }
      if (kind === 'image') {
        renderImage(blob, host, root);
        return;
      }
      setStatus(root, 'این نوع فایل در نمایشگر پشتیبانی نمی‌شود. دانلود خام غیرفعال است.');
    } catch (error) {
      setStatus(root, 'بارگذاری نمایشگر ناموفق بود.');
    }
  }
})();
