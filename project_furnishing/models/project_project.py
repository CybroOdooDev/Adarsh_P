from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    is_furnishing_project = fields.Boolean(
        string='Furnishing Project',
        default=False,
        index=True,
        help='Identifies projects managed within the Furnishing module.'
    )
    state = fields.Selection([
        ('to_do', 'To Do'),
        ('survey', 'Survey'),
        ('design', 'Design'),
        ('approved', 'Approved'),
        ('installation', 'Installation'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Project Status', default='to_do', required=True, tracking=True, copy=False)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='1', tracking=True)

    # Customer Address & Property Type
    site_address = fields.Text(
        string='Site Address',
        compute='_compute_site_address',
        store=True,
        readonly=False,
        help='Auto-populated from the selected customer address, but can be customized.'
    )
    property_type_id = fields.Many2one(
        'project.property.type',
        string='Property Type',
        tracking=True,
        index=True,
        help='Category of property (e.g. Luxury Villa, Penthouse, Commercial Office).'
    )

    # Dates
    scheduled_date = fields.Date(string='Scheduled Date', tracking=True)
    completion_date = fields.Date(string='Completion Date', tracking=True)

    # Budget Tab (Four Financial Fields - Margin % omitted)
    estimated_budget = fields.Monetary(
        string='Estimated Budget',
        currency_field='currency_id'
    )
    total_quoted_amount = fields.Monetary(
        string='Total Quoted Revenue',
        compute='_compute_total_quoted_amount',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Total untaxed revenue computed from linked non-cancelled Sales Orders and Quotations.'
    )
    total_cost_amount = fields.Monetary(
        string='Total Actual Cost',
        compute='_compute_total_cost_amount',
        store=True,
        readonly=True,
        currency_field='currency_id',
        help='Total untaxed cost computed from linked non-cancelled Purchase Orders.'
    )
    profit_margin = fields.Monetary(
        string='Profit Margin',
        compute='_compute_profit_margin',
        store=True,
        currency_field='currency_id'
    )

    # Warranty Tab
    has_warranty = fields.Boolean(
        string='Warranty / DLP Applicable',
        default=True,
        tracking=True,
        help='Toggle whether this project includes a Defects Liability Period (DLP) or warranty terms.'
    )
    warranty_start_date = fields.Date(string='Warranty Start Date')
    warranty_end_date = fields.Date(string='Warranty Expiry Date')
    retention_amount = fields.Monetary(
        string='Retention Held',
        currency_field='currency_id',
        help='Amount held by customer during Defects Liability Period (DLP).'
    )
    retention_release_date = fields.Date(string='Retention Due Date')
    warranty_notes = fields.Text(string='Warranty & Guarantee Terms')

    # Site Surveys
    survey_ids = fields.One2many(
        'project.site.survey',
        'project_id',
        string='Site Surveys'
    )
    survey_count = fields.Integer(
        string='Survey Count',
        compute='_compute_survey_count'
    )

    # Installations
    installation_ids = fields.One2many(
        'project.installation',
        'project_id',
        string='Installations'
    )
    installation_count = fields.Integer(
        string='Installation Count',
        compute='_compute_installation_count'
    )

    # Service & Warranty Requests
    service_request_ids = fields.One2many(
        'project.service.request',
        'project_id',
        string='Service Requests'
    )
    service_request_count = fields.Integer(
        string='Service Request Count',
        compute='_compute_service_request_count'
    )

    # Sales Orders & Quotations
    sale_order_ids = fields.One2many(
        'sale.order',
        'project_id',
        string='Sales Orders'
    )
    sale_order_count = fields.Integer(
        string='Sales Order Count',
        compute='_compute_sale_order_count'
    )

    # Purchase Orders
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'project_id',
        string='Purchase Orders'
    )

    @api.depends('partner_id')
    def _compute_site_address(self):
        for project in self:
            if project.partner_id:
                project.site_address = project.partner_id.contact_address or project.partner_id._display_address()
            elif not project.site_address:
                project.site_address = False

    @api.depends(
        'sale_order_ids.amount_untaxed',
        'sale_order_ids.state',
        'sale_order_ids.currency_id',
        'sale_order_id.amount_untaxed',
        'sale_order_id.state',
        'sale_order_id.currency_id',
    )
    def _compute_total_quoted_amount(self):
        for project in self:
            orders = project.sale_order_ids.filtered(lambda s: s.state != 'cancel')
            if project.sale_order_id and project.sale_order_id.state != 'cancel' and project.sale_order_id not in orders:
                orders |= project.sale_order_id
            total = 0.0
            for order in orders:
                if order.currency_id and project.currency_id and order.currency_id != project.currency_id:
                    total += order.currency_id._convert(
                        order.amount_untaxed,
                        project.currency_id,
                        project.company_id or self.env.company,
                        order.date_order or fields.Date.context_today(project)
                    )
                else:
                    total += order.amount_untaxed
            project.total_quoted_amount = total

    @api.depends(
        'purchase_order_ids.amount_untaxed',
        'purchase_order_ids.state',
        'purchase_order_ids.currency_id',
    )
    def _compute_total_cost_amount(self):
        for project in self:
            orders = project.purchase_order_ids.filtered(lambda p: p.state != 'cancel')
            total = 0.0
            for order in orders:
                if order.currency_id and project.currency_id and order.currency_id != project.currency_id:
                    total += order.currency_id._convert(
                        order.amount_untaxed,
                        project.currency_id,
                        project.company_id or self.env.company,
                        order.date_order or fields.Date.context_today(project)
                    )
                else:
                    total += order.amount_untaxed

            if project.account_id:
                direct_po_ids = orders.ids
                analytic_lines = self.env['purchase.order.line'].search([
                    ('analytic_distribution', 'in', project.account_id.ids),
                    ('order_id.state', '!=', 'cancel'),
                    ('order_id', 'not in', direct_po_ids),
                ])
                for line in analytic_lines:
                    line_po = line.order_id
                    if line_po.currency_id and project.currency_id and line_po.currency_id != project.currency_id:
                        total += line_po.currency_id._convert(
                            line.price_subtotal,
                            project.currency_id,
                            project.company_id or self.env.company,
                            line_po.date_order or fields.Date.context_today(project)
                        )
                    else:
                        total += line.price_subtotal

            project.total_cost_amount = total

    @api.depends('total_quoted_amount', 'total_cost_amount')
    def _compute_profit_margin(self):
        for project in self:
            project.profit_margin = (project.total_quoted_amount or 0.0) - (project.total_cost_amount or 0.0)

    def _compute_survey_count(self):
        survey_data = self.env['project.site.survey']._read_group(
            domain=[('project_id', 'in', self.ids)],
            groupby=['project_id'],
            aggregates=['__count']
        )
        data_map = {p.id: count for p, count in survey_data}
        for project in self:
            project.survey_count = data_map.get(project.id, 0)

    def _compute_installation_count(self):
        inst_data = self.env['project.installation']._read_group(
            domain=[('project_id', 'in', self.ids)],
            groupby=['project_id'],
            aggregates=['__count']
        )
        data_map = {p.id: count for p, count in inst_data}
        for project in self:
            project.installation_count = data_map.get(project.id, 0)

    def _compute_service_request_count(self):
        sr_data = self.env['project.service.request']._read_group(
            domain=[('project_id', 'in', self.ids)],
            groupby=['project_id'],
            aggregates=['__count']
        )
        data_map = {p.id: count for p, count in sr_data}
        for project in self:
            project.service_request_count = data_map.get(project.id, 0)

    def _compute_sale_order_count(self):
        so_data = self.env['sale.order']._read_group(
            domain=[('project_id', 'in', self.ids)],
            groupby=['project_id'],
            aggregates=['__count']
        )
        data_map = {p.id: count for p, count in so_data}
        for project in self:
            count = data_map.get(project.id, 0)
            if project.sale_order_id and project.sale_order_id.project_id.id != project.id:
                count += 1
            project.sale_order_count = count

    def _compute_purchase_orders_count(self):
        for project in self:
            po_ids = set(self.env['purchase.order'].search([('project_id', '=', project.id)]).ids)
            if project.account_id:
                line_po_ids = self.env['purchase.order.line'].search([
                    ('analytic_distribution', 'in', project.account_id.ids)
                ]).order_id.ids
                po_ids.update(line_po_ids)
            project.purchase_orders_count = len(po_ids)

    # Workflow Actions
    def action_create_task(self):
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(
                _("Cannot create tasks for cancelled project '%(project)s'.") % {
                    'project': self.name,
                }
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Task'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_company_id': self.company_id.id if self.company_id else False,
            },
        }

    def action_create_quotation(self):
        self.ensure_one()
        if self.state in ('to_do', 'cancelled'):
            raise UserError(
                _("Cannot create a quotation while the project is in '%(state)s' state.") % {
                    'state': dict(self._fields['state'].selection).get(self.state, self.state),
                }
            )
        if hasattr(self, 'allow_billable') and not self.allow_billable:
            self.allow_billable = True
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Quotation'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'default_project_id': self.id,
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'default_company_id': self.company_id.id if self.company_id else False,
            },
        }

    def action_create_survey(self):
        self.ensure_one()
        if self.state not in ('to_do', 'survey'):
            raise UserError(
                _("Site surveys can only be created for projects in 'To Do' or 'Survey' state. Project '%(project)s' is currently %(state)s.") % {
                    'project': self.name,
                    'state': dict(self._fields['state'].selection).get(self.state, self.state),
                }
            )
        open_surveys = self.survey_ids.filtered(lambda s: s.state not in ('completed', 'cancelled'))
        if open_surveys:
            raise UserError(
                _("Cannot create a new site survey for project '%(project)s' because an active survey '%(survey)s' is already in progress.\n\n"
                  "Please complete or cancel the existing survey before creating another.") % {
                    'project': self.name,
                    'survey': open_surveys[0].name,
                }
            )
        survey = self.env['project.site.survey'].create({
            'project_id': self.id,
            'address': self.site_address,
            'survey_date': fields.Date.context_today(self),
            'scheduled_date': self.scheduled_date or fields.Date.context_today(self),
        })
        self.state = 'survey'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Site Survey',
            'res_model': 'project.site.survey',
            'res_id': survey.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_proceed_to_design(self):
        for project in self:
            if project.state != 'survey':
                raise UserError(
                    _("Only projects in 'Survey' state can proceed to Design. Project '%(project)s' is currently %(state)s.") % {
                        'project': project.name,
                        'state': dict(self._fields['state'].selection).get(project.state, project.state),
                    }
                )
            completed_surveys = project.survey_ids.filtered(lambda s: s.state == 'completed')
            if not completed_surveys:
                raise UserError(_("Cannot proceed to Design because there are no completed site surveys. Please complete at least one survey first."))
            pending_surveys = project.survey_ids.filtered(lambda s: s.state not in ('completed', 'cancelled'))
            if pending_surveys:
                raise UserError(
                    _("Cannot proceed to Design for project '%(project)s' because all active site surveys must be completed first.\n\n"
                      "Pending survey(s): %(surveys)s") % {
                        'project': project.name,
                        'surveys': ", ".join(pending_surveys.mapped('name')),
                    }
                )
            project.state = 'design'

    def action_approve(self):
        for project in self:
            if project.state != 'design':
                raise UserError(
                    _("Only projects in 'Design' stage can be approved. Project '%(project)s' is currently %(state)s.") % {
                        'project': project.name,
                        'state': dict(self._fields['state'].selection).get(project.state, project.state),
                    }
                )
            project.state = 'approved'

    def action_create_installation(self):
        self.ensure_one()
        if self.state not in ('approved', 'installation'):
            raise UserError(
                _("Installations can only be created for projects in 'Approved' or 'Installation' state. Project '%(project)s' is currently %(state)s.") % {
                    'project': self.name,
                    'state': dict(self._fields['state'].selection).get(self.state, self.state),
                }
            )
        open_installations = self.installation_ids.filtered(lambda i: i.state not in ('completed', 'cancelled'))
        if open_installations:
            raise UserError(
                _("Cannot create a new installation for project '%(project)s' because an active installation '%(installation)s' is already in progress.\n\n"
                  "Please complete or cancel the existing installation first.") % {
                    'project': self.name,
                    'installation': open_installations[0].name,
                }
            )
        installation = self.env['project.installation'].create({
            'project_id': self.id,
            'address': self.site_address,
            'installer_id': self.env.user.id,
            'start_date': self.scheduled_date or fields.Date.context_today(self),
        })
        self.state = 'installation'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Installation',
            'res_model': 'project.installation',
            'res_id': installation.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_complete(self):
        for project in self:
            if project.state != 'installation':
                raise UserError(
                    _("Only projects in 'Installation' state can be completed. Project '%(project)s' is currently %(state)s.") % {
                        'project': project.name,
                        'state': dict(self._fields['state'].selection).get(project.state, project.state),
                    }
                )
            completed_installations = project.installation_ids.filtered(lambda inst: inst.state == 'completed')
            if not completed_installations:
                raise UserError(_("Cannot complete the project because there are no completed installations. Please complete at least one installation first."))
            pending_installations = project.installation_ids.filtered(lambda inst: inst.state not in ('completed', 'cancelled'))
            if pending_installations:
                raise UserError(
                    _("Cannot complete project '%(project)s' because all active installations must be completed first.\n\n"
                      "Pending installation(s): %(installations)s") % {
                        'project': project.name,
                        'installations': ", ".join(pending_installations.mapped('name')),
                    }
                )
            def is_task_finished(task):
                if hasattr(task, 'is_closed') and task.is_closed:
                    return True
                if hasattr(task, 'state') and task.state in ('1_done', '1_canceled'):
                    return True
                if task.stage_id and hasattr(task.stage_id, 'is_closed') and task.stage_id.is_closed:
                    return True
                return False

            unclosed_tasks = project.task_ids.filtered(lambda task: not is_task_finished(task))
            if unclosed_tasks:
                raise UserError(
                    _("Cannot complete project '%(project)s' because all tasks must be completed or cancelled first.\n\n"
                      "Pending task(s): %(tasks)s") % {
                        'project': project.name,
                        'tasks': ", ".join(unclosed_tasks.mapped('name')),
                    }
                )
            if not project.completion_date:
                project.completion_date = fields.Date.context_today(project)
            if project.has_warranty:
                if not project.warranty_start_date:
                    project.warranty_start_date = project.completion_date
                if not project.warranty_end_date:
                    project.warranty_end_date = project.warranty_start_date + relativedelta(years=1)
                if project.warranty_end_date < project.warranty_start_date:
                    raise UserError(
                        _("Cannot complete project '%(project)s' because Warranty Expiry Date cannot be earlier than Warranty Start Date.") % {
                            'project': project.name,
                        }
                    )
            project.state = 'completed'

    @api.constrains('has_warranty', 'state', 'warranty_start_date', 'warranty_end_date')
    def _check_warranty_dates(self):
        for project in self:
            if project.state == 'completed' and project.has_warranty:
                if not project.warranty_start_date or not project.warranty_end_date:
                    raise ValidationError(
                        _("Project '%(project)s' cannot be completed without specifying both Warranty Start Date and Warranty Expiry Date.") % {
                            'project': project.name,
                        }
                    )
                if project.warranty_end_date < project.warranty_start_date:
                    raise ValidationError(
                        _("For project '%(project)s', Warranty Expiry Date cannot be earlier than Warranty Start Date.") % {
                            'project': project.name,
                        }
                    )

    def action_cancel(self):
        for project in self:
            if project.state == 'completed':
                raise UserError(_("Completed project '%s' cannot be cancelled.") % project.name)
            # Cancel open installations
            open_installations = project.installation_ids.filtered(lambda i: i.state not in ('completed', 'cancelled'))
            if open_installations:
                open_installations.write({'state': 'cancelled'})
            # Cancel open surveys
            open_surveys = project.survey_ids.filtered(lambda s: s.state not in ('completed', 'cancelled'))
            if open_surveys:
                open_surveys.write({'state': 'cancelled'})
            # Cancel open service requests
            open_services = project.service_request_ids.filtered(lambda s: s.state not in ('resolved', 'cancelled'))
            if open_services:
                open_services.write({'state': 'cancelled'})
            project.state = 'cancelled'

    def action_reset_to_do(self):
        for project in self:
            if project.state not in ('cancelled', 'completed'):
                raise UserError(
                    _("Only cancelled or completed projects can be reset to To Do. Project '%(project)s' is currently %(state)s.") % {
                        'project': project.name,
                        'state': dict(self._fields['state'].selection).get(project.state, project.state),
                    }
                )
            project.state = 'to_do'

    def action_view_site_surveys(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Site Surveys',
            'res_model': 'project.site.survey',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_address': self.site_address,
            },
        }

    def action_view_installations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Installations',
            'res_model': 'project.installation',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_address': self.site_address,
            },
        }

    def action_view_service_requests(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        is_warranty_valid = bool(
            self.has_warranty and
            (not self.warranty_end_date or self.warranty_end_date >= today)
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Service Requests',
            'res_model': 'project.service.request',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_is_under_warranty': is_warranty_valid,
            },
        }

    def action_view_sale_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_quotations_with_onboarding')
        all_so_ids = list(set(self.sale_order_ids.ids + ([self.sale_order_id.id] if self.sale_order_id else [])))
        if len(all_so_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = all_so_ids[0]
        else:
            action['domain'] = [('id', 'in', all_so_ids)]
            action['views'] = [(False, 'list'), (False, 'form'), (False, 'kanban'), (False, 'pivot'), (False, 'graph')]
        action['context'] = {
            'default_project_id': self.id,
            'default_partner_id': self.partner_id.id if self.partner_id else False,
            'default_company_id': self.company_id.id if self.company_id else False,
            'search_default_my_quotation': 0,
        }
        return action

    def action_open_project_purchase_orders(self):
        self.ensure_one()
        all_po_ids = set(self.purchase_order_ids.ids)
        if self.account_id:
            analytic_po_ids = self.env['purchase.order.line'].search([
                ('analytic_distribution', 'in', self.account_id.ids)
            ]).order_id.ids
            all_po_ids.update(analytic_po_ids)
        action = self.env['ir.actions.act_window']._for_xml_id('purchase.purchase_form_action')
        all_po_ids = list(all_po_ids)
        if len(all_po_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = all_po_ids[0]
        else:
            action['domain'] = [('id', 'in', all_po_ids)]
            action['views'] = [(False, 'list'), (False, 'form'), (False, 'kanban'), (False, 'pivot'), (False, 'graph')]
        action['context'] = {
            'default_project_id': self.id,
            'default_company_id': self.company_id.id if self.company_id else False,
        }
        return action



