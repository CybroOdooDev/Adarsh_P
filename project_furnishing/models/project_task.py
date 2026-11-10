# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    @api.constrains('project_id')
    def _check_project_status(self):
        for task in self:
            if task.project_id and task.project_id.is_furnishing_project:
                if task.project_id.state == 'cancelled':
                    raise ValidationError(
                        _("Cannot create or assign tasks to cancelled furnishing project '%(project)s'.") % {
                            'project': task.project_id.name,
                        }
                    )
