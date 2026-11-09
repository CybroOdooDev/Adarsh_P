# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProjectInstallationTeam(models.Model):
    _name = 'project.installation.team'
    _description = 'Installation Team'
    _order = 'sequence, name'

    name = fields.Char(string='Team Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    leader_id = fields.Many2one(
        'res.users',
        string='Team Leader',
        index=True
    )
    member_ids = fields.Many2many(
        'res.users',
        'project_installation_team_member_rel',
        'team_id',
        'user_id',
        string='Members'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    installation_ids = fields.One2many(
        'project.installation',
        'team_id',
        string='Installations'
    )
    installation_count = fields.Integer(
        string='Installations Count',
        compute='_compute_installation_count'
    )

    def _compute_installation_count(self):
        inst_data = self.env['project.installation']._read_group(
            domain=[('team_id', 'in', self.ids)],
            groupby=['team_id'],
            aggregates=['__count']
        )
        data_map = {t.id: count for t, count in inst_data}
        for record in self:
            record.installation_count = data_map.get(record.id, 0)

    def action_view_installations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.installation',
            'view_mode': 'list,form',
            'domain': [('team_id', '=', self.id)],
            'context': {
                'default_team_id': self.id,
                'default_company_id': self.company_id.id if self.company_id else False,
            },
        }
