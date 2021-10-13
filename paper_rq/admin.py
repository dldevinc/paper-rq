from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.admin.checks import ModelAdminChecks
from django.contrib.admin.utils import model_ngettext, unquote
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from paper_admin.admin.filters import SimpleListFilter
from rq.job import JobStatus
from rq.queue import Queue
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
    clean_registries,
)
from rq.worker_registration import clean_worker_registry

from .helpers import get_all_queues, requeue_job
from .list_queryset import ListQuerySet
from .models import JobModel, QueueModel, WorkerModel


def clear_queue(queue: Queue):
    queue.empty()
    clean_registries(queue)
    clean_worker_registry(queue)


class RedisModelAdminChecks(ModelAdminChecks):
    def _check_ordering_item(self, obj, field_name, label):
        return []


class RedisModelAdminBase(admin.ModelAdmin):
    checks_class = RedisModelAdminChecks

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return self.has_manage_permission(request, obj)

    def has_manage_permission(self, request, obj=None):
        opts = self.model._meta
        return request.user.has_perm("%s.manage" % opts.app_label)

    def get_queryset(self, request):
        return self.model._default_manager.all()

    def get_object(self, request, object_id, from_field=None):
        model = self.model
        field = model._meta.pk if from_field is None else model._meta.get_field(from_field)
        try:
            object_id = field.to_python(object_id)
            return model._default_manager.get(**{field.name: object_id})
        except (model.DoesNotExist, ValidationError, ValueError):
            return None


def clear_queue_action(modeladmin, request, queryset):
    count = 0
    for queue_model in queryset:
        if queue_model.queue:
            clear_queue(queue_model.queue)
            count += 1

    messages.success(request, _("Successfully cleared %(count)d %(items)s.") % {
        "count": count,
        "items": model_ngettext(modeladmin.opts, count)
    })
clear_queue_action.short_description = _("Clear selected queues")


@admin.register(QueueModel)
class QueueModelAdmin(RedisModelAdminBase):
    fieldsets = (
        (None, {
            "fields": (
                "name",
            )
        }),
        (_("Server"), {
            "fields": (
                "location", "db_index"
            )
        }),
    )
    change_form_template = "paper_rq/queue_changeform.html"
    changelist_tools_template = "paper_rq/queue_changelist_tools.html"
    object_history = False
    ordering = ["order"]
    actions = [clear_queue_action]
    list_display = ["name", "queued_jobs", "started_jobs", "deferred_jobs",
                    "scheduled_jobs", "finished_jobs", "failed_jobs", "workers",
                    "location", "db_index"]

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        from django.urls import path

        info = self.model._meta.app_label, self.model._meta.model_name
        urlpatterns = super().get_urls()
        urlpatterns.insert(
            -1,
            path('<path:object_id>/clear/', self.admin_site.admin_view(self.clear_view), name='%s_%s_clear' % info),
        )
        return urlpatterns

    def clear_view(self, request, object_id):
        opts = self.model._meta

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        if not self.has_manage_permission(request, obj):
            raise PermissionDenied

        queue = obj.queue
        if queue:
            clear_queue(queue)

            self.message_user(
                request,
                _('The %(name)s “%(obj)s” was cleared successfully.') % {
                    'name': opts.verbose_name,
                    'obj': str(obj),
                },
                messages.SUCCESS,
            )

        info = self.model._meta.app_label, self.model._meta.model_name
        post_url = reverse("admin:%s_%s_changelist" % info, current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def queued_jobs(self, obj):
        if obj.queue:
            return obj.queue.count
    queued_jobs.short_description = _("Queued Jobs")

    def started_jobs(self, obj):
        if obj.queue:
            started_job_registry = StartedJobRegistry(obj.name, obj.queue.connection)
            return len(started_job_registry)
    started_jobs.short_description = _("Active Jobs")

    def deferred_jobs(self, obj):
        if obj.queue:
            deferred_job_registry = DeferredJobRegistry(obj.name, obj.queue.connection)
            return len(deferred_job_registry)
    deferred_jobs.short_description = _("Deferred Jobs")

    def scheduled_jobs(self, obj):
        if obj.queue:
            scheduled_job_registry = ScheduledJobRegistry(obj.name, obj.queue.connection)
            return len(scheduled_job_registry)
    scheduled_jobs.short_description = _("Scheduled Jobs")

    def finished_jobs(self, obj):
        if obj.queue:
            finished_job_registry = FinishedJobRegistry(obj.name, obj.queue.connection)
            return len(finished_job_registry)
    finished_jobs.short_description = _("Finished Jobs")

    def failed_jobs(self, obj):
        if obj.queue:
            failed_job_registry = FailedJobRegistry(obj.name, obj.queue.connection)
            return len(failed_job_registry)
    failed_jobs.short_description = _("Failed Jobs")

    def workers(self, obj):
        if obj.queue:
            info = WorkerModel._meta.app_label, WorkerModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.name,
                count=obj.worker_count
            )
    workers.short_description = _("Workers")
    workers.admin_order_field = "worker_count"
    workers.allow_tags = True

    def location(self, obj):
        if obj.queue:
            connection_kwargs = obj.queue.connection.connection_pool.connection_kwargs
            return "{0[host]}:{0[port]}".format(connection_kwargs)
    location.short_description = _("Location")

    def db_index(self, obj):
        if obj.queue:
            connection_kwargs = obj.queue.connection.connection_pool.connection_kwargs
            return connection_kwargs["db"]
    db_index.short_description = _("DB")


class WorkerQueueFilter(SimpleListFilter):
    parameter_name = "queue"
    title = _("Queue")
    template = "paper_admin/filters/radio.html"

    def lookups(self, request, model_admin):
        return [
            (queue.name, queue.name)
            for queue in get_all_queues()
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset

        return ListQuerySet(queryset.model, [
            worker
            for worker in queryset
            if worker.worker and any(queue in worker.worker.queue_names() for queue in value)
        ])


@admin.register(WorkerModel)
class WorkerModelAdmin(RedisModelAdminBase):
    fieldsets = (
        (None, {
            "fields": (
                "name", "queues",
            )
        }),
        (_("State"), {
            "fields": (
                "pid", "state", "job", "birth_date",
            )
        }),
        (_("Statistics"), {
            "fields": (
                "successful_job_count", "failed_job_count", "total_working_time"
            )
        }),
        (_("Server"), {
            "fields": (
                "location", "db_index"
            )
        }),
    )
    change_form_template = "paper_rq/worker_changeform.html"
    changelist_tools = False
    object_history = False
    list_filter = [WorkerQueueFilter]
    list_display = ["name", "pid", "state", "birth_date", "location", "db_index"]

    def has_delete_permission(self, request, obj=None):
        return False

    def queues(self, obj):
        if obj.worker:
            return ', '.join(obj.worker.queue_names())
    queues.short_description = _("Queues")

    def state(self, obj):
        if obj.worker:
            return obj.state
    state.short_description = _("State")

    def job(self, obj):
        if obj.worker:
            job = obj.worker.get_current_job()
            if job:
                info = JobModel._meta.app_label, JobModel._meta.model_name
                return format_html(
                    '<a href="{url}">{job}</a>',
                    url=reverse("admin:%s_%s_change" % info, args=(job.id, )),
                    job=job.id
                )

        return "-"
    job.short_description = _("Current job")

    def successful_job_count(self, obj):
        if obj.worker:
            return obj.worker.successful_job_count
    successful_job_count.short_description = _("Successful job count")

    def failed_job_count(self, obj):
        if obj.worker:
            return obj.worker.failed_job_count
    failed_job_count.short_description = _("Failed job count")

    def total_working_time(self, obj):
        if obj.worker:
            return obj.worker.total_working_time
    total_working_time.short_description = _("Total working time")

    def location(self, obj):
        if obj.worker:
            connection_kwargs = obj.worker.connection.connection_pool.connection_kwargs
            return "{0[host]}:{0[port]}".format(connection_kwargs)
    location.short_description = _("Location")

    def db_index(self, obj):
        if obj.worker:
            connection_kwargs = obj.worker.connection.connection_pool.connection_kwargs
            return connection_kwargs["db"]
    db_index.short_description = _("DB")


class JobQueueFilter(SimpleListFilter):
    parameter_name = "queue"
    title = _("Queue")
    template = "paper_admin/filters/radio.html"

    def lookups(self, request, model_admin):
        return [
            (queue.name, queue.name)
            for queue in get_all_queues()
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset

        return ListQuerySet(queryset.model, [
            job
            for job in queryset
            if job.job and any(queue == job.job.origin for queue in value)
        ])


class JobStatusFilter(SimpleListFilter):
    parameter_name = "status"
    title = _("Status")
    template = "paper_admin/filters/checkbox.html"

    def lookups(self, request, model_admin):
        return (
            (JobStatus.QUEUED, _("Queued")),
            (JobStatus.DEFERRED, _("Deferred")),
            (JobStatus.SCHEDULED, _("Scheduled")),
            (JobStatus.STARTED, _("Started")),
            (JobStatus.FINISHED, _("Finished")),
            (JobStatus.FAILED, _("Failed")),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset

        return ListQuerySet(queryset.model, [
            job
            for job in queryset
            if job.status in value
        ])


def requeue_job_action(modeladmin, request, queryset):
    count = 0
    for job_model in queryset:
        if job_model.job:
            requeue_job(job_model.job)
            count += 1

    messages.success(request, _("Successfully enqueued %(count)d %(items)s.") % {
        "count": count,
        "items": model_ngettext(modeladmin.opts, count)
    })
requeue_job_action.short_description = _("Requeue selected jobs")


@admin.register(JobModel)
class JobModelAdmin(RedisModelAdminBase):
    fieldsets = (
        (None, {
            "fields": (
                "id", "description", "queue", "dependency", "original", "timeout", "ttl", "status",
            )
        }),
        (_("Callable"), {
            "fields": (
                "callable_display", "result_display", "exception_display", "meta_display",
            )
        }),
        (_("Important Dates"), {
            "fields": (
                "created_at", "enqueued_at", "ended_at"
            )
        }),
    )
    change_form_template = "paper_rq/job_changeform.html"
    changelist_tools_template = "paper_rq/job_changelist_tools.html"
    object_history = False
    actions = [requeue_job_action]
    ordering = ["-created_at"]
    search_fields = ["pk", "callable", "result", "exception"]
    list_filter = [JobQueueFilter, JobStatusFilter]
    list_display = ["id", "queue", "status", "enqueued_at", "created_at"]

    def get_urls(self):
        from django.urls import path

        info = self.model._meta.app_label, self.model._meta.model_name
        urlpatterns = super().get_urls()
        urlpatterns.insert(
            -1,
            path('<path:object_id>/requeue/', self.admin_site.admin_view(self.requeue_view), name='%s_%s_requeue' % info),
        )
        return urlpatterns

    def get_search_results(self, request, queryset, search_term):
        search_fields = self.get_search_fields(request)
        if search_fields and search_term:
            search_term = search_term.lower()

            # collect IDs of matching jobs
            object_ids = set()
            for fieldname in search_fields:
                filtered = filter(
                    lambda m: (getattr(m, fieldname) or "").lower().find(search_term) >= 0,
                    queryset,
                )
                object_ids.update(m.pk for m in filtered)

            # filter job with preserved order
            object_list = (item for item in queryset if item.pk in object_ids)
            queryset = type(queryset)(queryset.model, object_list)

        return queryset, False

    def requeue_view(self, request, object_id):
        opts = self.model._meta
        info = opts.app_label, opts.model_name

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        if not self.has_manage_permission(request, obj):
            raise PermissionDenied

        job = obj.job
        if job:
            new_job = requeue_job(job)

            self.message_user(
                request,
                _('The %(name)s “%(obj)s” was requeued successfully.') % {
                    'name': opts.verbose_name,
                    'obj': str(obj),
                },
                messages.SUCCESS,
            )
            post_url = reverse("admin:%s_%s_change" % info, args=[new_job.id], current_app=self.admin_site.name)
            return HttpResponseRedirect(post_url)

        post_url = reverse("admin:%s_%s_changelist" % info, current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def delete_view(self, request, object_id, extra_context=None):
        opts = self.model._meta

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        if not self.has_manage_permission(request, obj):
            raise PermissionDenied

        job = obj.job
        if job:
            job.delete()

            self.message_user(
                request,
                _('The %(name)s “%(obj)s” was deleted successfully.') % {
                    'name': opts.verbose_name,
                    'obj': str(obj),
                },
                messages.SUCCESS,
            )

        info = self.model._meta.app_label, self.model._meta.model_name
        post_url = reverse("admin:%s_%s_changelist" % info, current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def delete_queryset(self, request, queryset):
        for job_model in queryset:
            if job_model.job:
                job_model.job.delete()

    def status(self, obj):
        if obj.job:
            return obj.status
    status.short_description = _("Status")

    def dependency(self, obj):
        if obj.job:
            dependency_id = obj.job._dependency_id
            if dependency_id:
                info = JobModel._meta.app_label, JobModel._meta.model_name
                return format_html(
                    '<a href="{url}">{job}</a>',
                    url=reverse("admin:%s_%s_change" % info, args=(dependency_id,)),
                    job=dependency_id
                )

        return "-"
    dependency.short_description = _("Depends On")

    def original(self, obj):
        if obj.job:
            orig_job_id = obj.job.meta.get("original_job")
            if orig_job_id:
                info = JobModel._meta.app_label, JobModel._meta.model_name
                return format_html(
                    '<a href="{url}">{job}</a>',
                    url=reverse("admin:%s_%s_change" % info, args=(orig_job_id,)),
                    job=orig_job_id
                )

        return "-"
    original.short_description = _("Requeued From")

    def ttl(self, obj):
        if obj.job:
            seconds = obj.job.connection.ttl(obj.job.key)
            if seconds == -1:
                return "Infinite"
            return timedelta(seconds=seconds)
    ttl.short_description = _("TTL")

    def callable_display(self, obj):
        return format_html("<code>{}</code>", obj.callable)
    callable_display.short_description = JobModel._meta.get_field("callable").verbose_name

    def result_display(self, obj):
        if obj.result:
            return format_html("<pre>{}</pre>", obj.result)
        return "-"
    result_display.short_description = JobModel._meta.get_field("result").verbose_name

    def exception_display(self, obj):
        if obj.exception:
            return format_html("<pre>{}</pre>", obj.exception)
        return "-"
    exception_display.short_description = JobModel._meta.get_field("exception").verbose_name

    def meta_display(self, obj):
        if obj.meta:
            return obj.meta
        return "-"
    meta_display.short_description = JobModel._meta.get_field("meta").verbose_name
