import math
from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.admin.checks import ModelAdminChecks
from django.contrib.admin.utils import display_for_value, model_ngettext, unquote
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from paper_admin.admin.filters import SimpleListFilter
from rq.job import JobStatus
from rq.queue import Queue
from rq.registry import (
    CanceledJobRegistry,
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
    clean_registries,
)
from rq.results import Result
from rq.worker_registration import clean_worker_registry

from . import helpers
from .exceptions import UnsupportedJobStatusError
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


@admin.display(
    description=_("Clear selected queues")
)
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


@admin.register(QueueModel)
class QueueModelAdmin(RedisModelAdminBase):
    fieldsets = (
        (None, {
            "fields": (
                "name", "view_workers",
            )
        }),
        (_("Jobs"), {
            "fields": (
                "view_queued_jobs", "view_started_jobs", "view_deferred_jobs",
                "view_scheduled_jobs", "view_finished_jobs", "view_failed_jobs",
                "view_canceled_jobs",
            )
        }),
        (_("Server"), {
            "fields": (
                "view_location", "view_db_index"
            )
        }),
    )
    change_form_template = "paper_rq/queue_changeform.html"
    changelist_tools_template = "paper_rq/queue_changelist_tools.html"
    object_history = False
    ordering = ["order"]
    actions = [clear_queue_action]
    list_display = ["name", "view_queued_jobs", "view_started_jobs", "view_deferred_jobs",
                    "view_scheduled_jobs", "view_finished_jobs", "view_failed_jobs",
                    "view_canceled_jobs", "view_workers", "view_location", "view_db_index"]

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
                _("The %(name)s “%(obj)s” was cleared successfully.") % {
                    "name": opts.verbose_name,
                    "obj": str(obj),
                },
                messages.SUCCESS,
            )

        info = self.model._meta.app_label, self.model._meta.model_name
        post_url = reverse("admin:%s_%s_changelist" % info, current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    @admin.display(
        description=_("Queued Jobs"),
        ordering="queue.count"
    )
    def view_queued_jobs(self, obj):
        if obj.queue:
            info = JobModel._meta.app_label, JobModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}&status={status}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.queue.name,
                status=JobStatus.QUEUED.value,
                count=obj.queue.count
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Active Jobs"),
    )
    def view_started_jobs(self, obj):
        if obj.queue:
            started_job_registry = StartedJobRegistry(obj.name, obj.queue.connection)
            info = JobModel._meta.app_label, JobModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}&status={status}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.queue.name,
                status=JobStatus.STARTED.value,
                count=len(started_job_registry)
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Deferred Jobs"),
    )
    def view_deferred_jobs(self, obj):
        if obj.queue:
            deferred_job_registry = DeferredJobRegistry(obj.name, obj.queue.connection)
            info = JobModel._meta.app_label, JobModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}&status={status}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.queue.name,
                status=JobStatus.DEFERRED.value,
                count=len(deferred_job_registry)
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Scheduled Jobs"),
    )
    def view_scheduled_jobs(self, obj):
        if obj.queue:
            scheduled_job_registry = ScheduledJobRegistry(obj.name, obj.queue.connection)
            info = JobModel._meta.app_label, JobModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}&status={status}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.queue.name,
                status=JobStatus.SCHEDULED.value,
                count=len(scheduled_job_registry)
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Finished Jobs"),
    )
    def view_finished_jobs(self, obj):
        if obj.queue:
            finished_job_registry = FinishedJobRegistry(obj.name, obj.queue.connection)
            info = JobModel._meta.app_label, JobModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}&status={status}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.queue.name,
                status=JobStatus.FINISHED.value,
                count=len(finished_job_registry)
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Failed Jobs"),
    )
    def view_failed_jobs(self, obj):
        if obj.queue:
            failed_job_registry = FailedJobRegistry(obj.name, obj.queue.connection)
            info = JobModel._meta.app_label, JobModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}&status={status}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.queue.name,
                status=JobStatus.FAILED.value,
                count=len(failed_job_registry)
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Canceled Jobs"),
    )
    def view_canceled_jobs(self, obj):
        if obj.queue:
            canceled_job_registry = CanceledJobRegistry(obj.name, obj.queue.connection)
            info = JobModel._meta.app_label, JobModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}&status={status}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.queue.name,
                status=JobStatus.CANCELED.value,
                count=len(canceled_job_registry)
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Workers"),
        ordering="worker_count",
    )
    def view_workers(self, obj):
        if obj.queue:
            info = WorkerModel._meta.app_label, WorkerModel._meta.model_name
            return format_html(
                '<a href="{url}?queue={queue}">{count}</a>',
                url=reverse("admin:%s_%s_changelist" % info),
                queue=obj.name,
                count=obj.worker_count
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Location"),
    )
    def view_location(self, obj):
        if obj.queue:
            connection_kwargs = obj.queue.connection.connection_pool.connection_kwargs
            return "{host}:{port}".format(
                host=connection_kwargs.get("host", "localhost"),
                port=connection_kwargs.get("port", 6379),
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("DB"),
    )
    def view_db_index(self, obj):
        if obj.queue:
            connection_kwargs = obj.queue.connection.connection_pool.connection_kwargs
            return connection_kwargs["db"]
        return self.get_empty_value_display()


class WorkerQueueFilter(SimpleListFilter):
    parameter_name = "queue"
    title = _("Queue")
    template = "paper_admin/filters/radio.html"

    def lookups(self, request, model_admin):
        return [
            (queue.name, queue.name)
            for queue in helpers.get_all_queues()
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
                "name", "view_queues"
            )
        }),
        (_("State"), {
            "fields": (
                "view_state", "view_current_job",
            )
        }),
        (_("Statistics"), {
            "fields": (
                "view_successful_job_count", "view_failed_job_count",
                "view_total_working_time"
            )
        }),
        (_("Process"), {
            "fields": (
                "pid", "hostname", "ip_address", "view_birth_date", "view_last_heartbeat"
            )
        }),
        (_("Redis server"), {
            "fields": (
                "view_location", "view_db_index"
            )
        }),
    )
    change_form_template = "paper_rq/worker_changeform.html"
    object_history = False
    list_filter = [WorkerQueueFilter]
    list_display = ["name", "pid", "hostname", "view_state", "view_birth_date",
                    "view_location", "view_db_index"]

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(
        description=_("Queues")
    )
    def view_queues(self, obj):
        if obj.worker:
            return ', '.join(obj.worker.queue_names())
        return self.get_empty_value_display()

    @admin.display(
        description=_("State")
    )
    def view_state(self, obj):
        if obj.worker:
            return obj.state
        return self.get_empty_value_display()

    @admin.display(
        description=_("Current job")
    )
    def view_current_job(self, obj):
        if obj.worker:
            job = obj.worker.get_current_job()
            if job:
                info = JobModel._meta.app_label, JobModel._meta.model_name
                return format_html(
                    '<a href="{url}">{job}</a>',
                    url=reverse("admin:%s_%s_change" % info, args=(job.id, )),
                    job=job.id
                )
        return self.get_empty_value_display()

    @admin.display(
        description=_("Successful job count")
    )
    def view_successful_job_count(self, obj):
        if obj.worker:
            return obj.worker.successful_job_count
        return self.get_empty_value_display()

    @admin.display(
        description=_("Failed job count")
    )
    def view_failed_job_count(self, obj):
        if obj.worker:
            return obj.worker.failed_job_count
        return self.get_empty_value_display()

    @admin.display(
        description=_("Total working time")
    )
    def view_total_working_time(self, obj):
        if obj.worker:
            return obj.worker.total_working_time
        return self.get_empty_value_display()

    def _view_datetime(self, date):
        if date:
            return format_html(
                '<span title="{full_time}">{humanized_time}</span>',
                humanized_time=naturaltime(date),
                full_time=display_for_value(date, self.get_empty_value_display())
            )
        else:
            return self.get_empty_value_display()

    @admin.display(
        description=WorkerModel._meta.get_field("birth_date").verbose_name,
        ordering="birth_date"
    )
    def view_birth_date(self, obj):
        return self._view_datetime(obj.birth_date)

    @admin.display(
        description=WorkerModel._meta.get_field("last_heartbeat").verbose_name,
        ordering="last_heartbeat"
    )
    def view_last_heartbeat(self, obj):
        return self._view_datetime(obj.last_heartbeat)

    @admin.display(
        description=_("Location")
    )
    def view_location(self, obj):
        if obj.worker:
            connection_kwargs = obj.worker.connection.connection_pool.connection_kwargs
            return "{host}:{port}".format(
                host=connection_kwargs.get("host", "localhost"),
                port=connection_kwargs.get("port", 6379),
            )
        return self.get_empty_value_display()

    @admin.display(
        description=_("DB")
    )
    def view_db_index(self, obj):
        if obj.worker:
            connection_kwargs = obj.worker.connection.connection_pool.connection_kwargs
            return connection_kwargs["db"]
        return self.get_empty_value_display()


class JobQueueFilter(SimpleListFilter):
    parameter_name = "queue"
    title = _("Queue")
    template = "paper_admin/filters/radio.html"

    def lookups(self, request, model_admin):
        return [
            (queue.name, queue.name)
            for queue in helpers.get_all_queues()
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
            (JobStatus.QUEUED.value, _("Queued")),
            (JobStatus.DEFERRED.value, _("Deferred")),
            (JobStatus.SCHEDULED.value, _("Scheduled")),
            (JobStatus.STARTED.value, _("Started")),
            (JobStatus.FINISHED.value, _("Finished")),
            (JobStatus.FAILED.value, _("Failed")),
            (JobStatus.STOPPED.value, _("Stopped")),
            (JobStatus.CANCELED.value, _("Canceled")),
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


@admin.display(
    description=_("Requeue selected jobs")
)
def requeue_job_action(modeladmin, request, queryset):
    count = 0
    for job_model in queryset:
        job = job_model.job
        if job:
            helpers.requeue_job(job)
            count += 1

    messages.success(request, _("Successfully enqueued %(count)d %(items)s.") % {
        "count": count,
        "items": model_ngettext(modeladmin.opts, count)
    })


@admin.display(
    description=_("Stop selected jobs")
)
def stop_job_action(modeladmin, request, queryset):
    count = 0
    for job_model in queryset:
        job = job_model.job
        if job is not None:
            try:
                helpers.stop_job(job)
            except UnsupportedJobStatusError:
                pass
            else:
                count += 1

    messages.success(request, _("Successfully stopped %(count)d %(items)s.") % {
        "count": count,
        "items": model_ngettext(modeladmin.opts, count)
    })


@admin.register(JobModel)
class JobModelAdmin(RedisModelAdminBase):
    fieldsets = (
        (None, {
            "fields": (
                "id", "description", "queue", "view_depends_on", "timeout",
                "view_ttl", "view_status",
            )
        }),
        (_("Callable"), {
            "fields": (
                "view_callable", "view_meta",
            )
        }),
        (_("Result"), {
            "fields": (
                "view_result", "view_exception",
            )
        }),
        (_("Important Dates"), {
            "fields": (
                "view_created_at", "view_scheduled_on", "view_enqueued_at",
                "view_started_at", "view_ended_at", "view_duration"
            )
        }),
    )
    change_form_template = "paper_rq/job_changeform.html"
    changelist_tools_template = "paper_rq/job_changelist_tools.html"
    object_history = False
    actions = [requeue_job_action, stop_job_action]
    ordering = ["-enqueue_time"]
    search_fields = ["pk", "callable", "result", "exception"]
    list_filter = [JobQueueFilter, JobStatusFilter]
    list_display = ["view_id", "view_short_callable", "queue", "view_status",
                    "view_enqueued_at", "view_duration"]
    tabs = [
        ('general', _('General')),
        ('results', _('Latest results')),
    ]
    form_includes = [
        ("paper_rq/job_results.html", "top", "results"),
    ]

    def get_urls(self):
        from django.urls import path

        info = self.model._meta.app_label, self.model._meta.model_name
        urlpatterns = super().get_urls()
        urlpatterns.insert(
            -1,
            path('<path:object_id>/requeue/', self.admin_site.admin_view(self.requeue_view), name='%s_%s_requeue' % info),
        )
        urlpatterns.insert(
            -1,
            path('<path:object_id>/stop/', self.admin_site.admin_view(self.stop_view), name='%s_%s_stop' % info),
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
                    lambda m: str(getattr(m, fieldname)).lower().find(search_term) >= 0,
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
            new_job = helpers.requeue_job(job)

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

    def stop_view(self, request, object_id):
        opts = self.model._meta
        info = opts.app_label, opts.model_name

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        if not self.has_manage_permission(request, obj):
            raise PermissionDenied

        try:
            helpers.stop_job(obj.job)
        except UnsupportedJobStatusError as exc:
            self.message_user(
                request,
                _("The %(name)s “%(obj)s” has status “%(status)s” and cannot be stopped.") % {
                    "name": opts.verbose_name,
                    "obj": str(obj),
                    "status": exc.status
                },
                messages.WARNING,
            )

        post_url = request.GET.get("next")
        post_url = post_url or reverse("admin:%s_%s_changelist" % info, current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def delete_view(self, request, object_id, extra_context=None):
        opts = self.model._meta
        info = opts.app_label, opts.model_name

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        if not self.has_manage_permission(request, obj):
            raise PermissionDenied

        job = obj.job
        if job:
            if helpers.supports_redis_streams(job.connection):
                with job.connection.pipeline() as pipe:
                    pipe.delete(Result.get_key(job.id))
                    job.delete(pipeline=pipe)
                    pipe.execute()
            else:
                job.delete()

            self.message_user(
                request,
                _("The %(name)s “%(obj)s” was deleted successfully.") % {
                    "name": opts.verbose_name,
                    "obj": str(obj),
                },
                messages.SUCCESS,
            )

        post_url = request.GET.get("next")
        post_url = post_url or reverse("admin:%s_%s_changelist" % info, current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def delete_queryset(self, request, queryset):
        for job_model in queryset:
            job = job_model.job
            if job:
                job.delete()

    @admin.display(
        description=_("ID"),
        ordering="id"
    )
    def view_id(self, obj):
        if obj.invalid:
            icon_url = staticfiles_storage.url("paper_rq/invalid.svg")
            return format_html("<img src=\"{}\" width=20 height=20 class=\"align-text-bottom\" alt=\"\">"
                               "<span class=\"ml-1\">{}</span>", icon_url, obj.id)
        return obj.id

    @admin.display(
        description=_("Depends On"),
    )
    def view_depends_on(self, obj):
        if obj.job:
            dependency_id = obj.job._dependency_id
            if dependency_id:
                info = JobModel._meta.app_label, JobModel._meta.model_name
                return format_html(
                    '<a href="{url}">{job}</a>',
                    url=reverse("admin:%s_%s_change" % info, args=(dependency_id,)),
                    job=dependency_id
                )
        return self.get_empty_value_display()

    @admin.display(
        description=_("TTL"),
    )
    def view_ttl(self, obj):
        if obj.job:
            seconds = obj.job.connection.ttl(obj.job.key)
            if seconds == -1:
                return "Infinite"
            return timedelta(seconds=seconds)

    @admin.display(
        description=_("Status"),
    )
    def view_status(self, obj):
        if obj.job:
            return obj.status.value

    @admin.display(
        description=JobModel._meta.get_field("callable").verbose_name,
    )
    def view_short_callable(self, obj):
        if obj.invalid:
            return self.get_empty_value_display()

        job = obj.job
        full_path = helpers.get_job_func_repr(job)
        short_path = helpers.get_job_func_short_repr(job)

        return format_html(
            '<span title="{full_path}">{short_path}</span>',
            short_path=short_path,
            full_path=full_path
        )

    @admin.display(
        description=JobModel._meta.get_field("callable").verbose_name,
    )
    def view_callable(self, obj):
        if obj.invalid:
            icon_url = staticfiles_storage.url("paper_rq/invalid.svg")
            return format_html("<code>"
                               "<img src=\"{}\" width=20 height=20 alt=\"\">"
                               "<span class=\"align-text-top ml-1\">{}</span>"
                               "</code>", icon_url, _("Deserialization error"))
        return format_html("<code>{}</code>", obj.callable)

    @admin.display(
        description=JobModel._meta.get_field("meta").verbose_name,
    )
    def view_meta(self, obj):
        return obj.meta or self.get_empty_value_display()

    @admin.display(
        description=JobModel._meta.get_field("result").verbose_name,
    )
    def view_result(self, obj):
        if obj.result:
            return format_html("<pre>{}</pre>", obj.result)
        return self.get_empty_value_display()

    @admin.display(
        description=JobModel._meta.get_field("exception").verbose_name,
    )
    def view_exception(self, obj):
        if obj.exception:
            return format_html("<pre>{}</pre>", obj.exception)
        return self.get_empty_value_display()

    def _view_datetime(self, date):
        if date:
            return format_html(
                '<span title="{full_time}">{humanized_time}</span>',
                humanized_time=naturaltime(date),
                full_time=display_for_value(date, self.get_empty_value_display())
            )
        else:
            return self.get_empty_value_display()

    @admin.display(
        description=JobModel._meta.get_field("created_at").verbose_name,
        ordering="created_at"
    )
    def view_created_at(self, obj):
        return self._view_datetime(obj.created_at)

    @admin.display(
        description=_("Scheduled on"),
    )
    def view_scheduled_on(self, obj):
        if not obj.job.is_scheduled:
            return self.get_empty_value_display()

        scheduler = helpers.get_job_scheduler(obj.job)
        if not scheduler:
            return self.get_empty_value_display()

        for job, scheduled_on in scheduler.get_jobs(with_times=True):
            if job.origin == obj.job.origin and job.id == obj.id:
                utc_time = helpers.format_datetime(scheduled_on)
                return self._view_datetime(utc_time)

        return self.get_empty_value_display()

    @admin.display(
        description=JobModel._meta.get_field("enqueued_at").verbose_name,
        ordering="enqueue_time"
    )
    def view_enqueued_at(self, obj):
        return self._view_datetime(obj.enqueued_at)

    @admin.display(
        description=JobModel._meta.get_field("started_at").verbose_name,
        ordering="started_at"
    )
    def view_started_at(self, obj):
        return self._view_datetime(obj.started_at)

    @admin.display(
        description=JobModel._meta.get_field("ended_at").verbose_name,
        ordering="ended_at"
    )
    def view_ended_at(self, obj):
        return self._view_datetime(obj.ended_at)

    @admin.display(
        description=_("Duration"),
    )
    def view_duration(self, obj):
        duration = obj.duration
        if duration:
            total_seconds = int(duration.total_seconds())
            microseconds = math.ceil(duration.microseconds / 1000)
            if not total_seconds:
                return "{}ms".format(microseconds)
            elif total_seconds < 5:
                return "{}.{:03}s".format(total_seconds, microseconds)
            elif total_seconds < 60:
                return "{}s".format(total_seconds)
            else:
                return timedelta(seconds=math.ceil(total_seconds))
        return self.get_empty_value_display()
