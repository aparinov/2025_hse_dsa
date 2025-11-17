from django.db.models import Count, Q
from .models import Project


def get_recommended_projects(user):
    """
    Возвращает рекомендованные проекты для пользователя на основе совпадения тегов.
    
    Алгоритм:
    1. Получаем интересы пользователя (теги)
    2. Находим проекты, у которых есть совпадающие теги
    3. Сортируем по количеству совпадений
    4. Фильтруем только проекты со статусом RECRUITMENT
    5. Исключаем проекты, где пользователь уже участвует или является создателем
    
    Args:
        user: Объект пользователя
        
    Returns:
        QuerySet проектов, отсортированных по релевантности
    """
    # Получаем интересы пользователя
    user_interests = user.interests.all()
    
    # Если у пользователя нет интересов, возвращаем пустой QuerySet
    if not user_interests.exists():
        return Project.objects.none()
    
    # Находим проекты с совпадающими тегами
    recommended = Project.objects.filter(
        tags__in=user_interests,  # Проекты с тегами из интересов пользователя
        status=Project.Status.RECRUITMENT  # Только проекты с открытым набором
    ).exclude(
        Q(creator=user) | Q(participants=user)  # Исключаем проекты пользователя
    ).annotate(
        matching_tags=Count('tags', filter=Q(tags__in=user_interests))  # Считаем совпадения
    ).order_by(
        '-matching_tags',  # Сортируем по количеству совпадающих тегов
        '-created_at'  # При равном количестве - по дате создания
    ).distinct()  # Убираем дубликаты
    
    return recommended

