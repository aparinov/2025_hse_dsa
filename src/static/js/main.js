// Используем IIFE (Immediately Invoked Function Expression)
// для изоляции нашего кода и предотвращения засорения глобальной области видимости.
(function() {
    'use strict';

    // Этот код выполнится, когда DOM будет полностью загружен.
    document.addEventListener('DOMContentLoaded', function() {
        
        console.log('DOM fully loaded and parsed. Custom JS file is working.');

        // Сюда в будущем можно будет добавлять код для:
        // - отправки AJAX-запросов (например, для подачи заявки без перезагрузки страницы)
        // - добавления интерактивных элементов
        // - валидации форм на стороне клиента

    });

})();
