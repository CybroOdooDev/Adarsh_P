from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    is_furnishing_project = fields.Boolean(
        string='Furnishing Project',
        default=True,
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
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', default='0', tracking=True)

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
        currency_field='currency_id'
    )
    total_cost_amount = fields.Monetary(
        string='Total Actual Cost',
        currency_field='currency_id'
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

    @api.depends('partner_id')
    def _compute_site_address(self):
        for project in self:
            if project.partner_id:
                project.site_address = project.partner_id.contact_address or project.partner_id._display_address()
            elif not project.site_address:
                project.site_address = False

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

    # Workflow Actions
    def action_create_task(self):
        self.ensure_one()
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

    def action_create_survey(self):
        self.ensure_one()
        survey = self.env['project.site.survey'].create({
            'project_id': self.id,
            'address': self.site_address,
            'survey_date': fields.Date.context_today(self),
            'scheduled_date': self.scheduled_date or fields.Date.context_today(self),
        })
        if self.state in ('draft', 'to_do'):
            self.state = 'survey'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Site Survey',
            'res_model': 'project.site.survey',
            'res_id': survey.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_approve(self):
        for project in self:
            project.state = 'approved'

    def action_create_installation(self):
        self.ensure_one()
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
            if not project.installation_ids:
                raise UserError(_("Cannot complete the project because there are no installations. Please create and complete at least one installation first."))
            uncompleted = project.installation_ids.filtered(lambda inst: inst.state != 'completed')
            if uncompleted:
                raise UserError(
                    _("Cannot complete project '%(project)s' because all installations must be completed first.\n\n"
                      "Pending installation(s): %(installations)s") % {
                        'project': project.name,
                        'installations': ", ".join(uncompleted.mapped('name')),
                    }
                )
            project.state = 'completed'
            if not project.completion_date:
                project.completion_date = fields.Date.context_today(project)

    def action_cancel(self):
        for project in self:
            project.state = 'cancelled'

    def action_reset_draft(self):
        for project in self:
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
        return {
            'type': 'ir.actions.act_window',
            'name': 'Service Requests',
            'res_model': 'project.service.request',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_is_under_warranty': self.has_warranty,
            },
        }

