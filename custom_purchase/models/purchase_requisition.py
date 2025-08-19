from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class PurchaseRequisition(models.Model):
    _name = 'purchase.requisition.custom'
    _description = 'Purchase Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Requisition Reference', required=False, copy=False, readonly=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('purchase.requisition.custom'))

    vendor_id = fields.Many2one('res.partner', string='Preferred Vendor', domain=[('supplier_rank', '>', 0)])
    requester_id = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user, readonly=True)
    department = fields.Many2one(comodel_name='hr.department', string='Department')
    purchase_requisition_line_ids = fields.One2many(comodel_name="purchase.requisition.custom.lines",
                                       inverse_name="purchase_requisition_id",
                                       string="Requisition ID", required=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('reviewed', 'Reviewed'),
        ('approved', 'Approved'),
        ('authorized', 'Authorized'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', track_visibility='onchange')


    def action_submitted_button(self):
        self.write({'state': 'submitted'})
        return True

    def action_review_manager(self):
        self.write({'state': 'reviewed'})
        return True


    def action_back_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_approved_manager(self):
        self.write({'state': 'approved'})
        return True


    def action_authorized(self):
        PurchaseOrder = self.env['purchase.order']
        PurchaseOrderLine = self.env['purchase.order.line']

        for requisition in self:
            if not requisition.vendor_id:
                raise UserError("Preferred Vendor must be selected to create a Purchase Order.")

            # Create the Purchase Order
            po = PurchaseOrder.create({
                'partner_id': requisition.vendor_id.id,
                'origin': requisition.name,
                'order_line': [],
            })

            # Create lines from the requisition lines
            for line in requisition.purchase_requisition_line_ids:
                product = line.item_description.product_variant_id

                if not product:
                    raise UserError(f"Product '{line.item_description.name}' has no product variant.")

                PurchaseOrderLine.create({
                    'order_id': po.id,
                    'product_id': product.id,
                    'name': line.specifications or line.item_description.name,
                    'product_qty': line.quantity,
                    'price_unit': line.estimated_cost,
                    'product_uom': product.uom_id.id,
                    'date_planned': fields.Date.today(),
                })

            requisition.write({'state': 'authorized'})

        return True

    def action_reject(self):
        self.write({'state': 'rejected'})
        return True

    def write(self, vals):
        user = self.env.user
        for rec in self:
            if user.has_group('custom_purchase.group_purchase_requisition_staff') and rec.state != 'draft':
                raise UserError("Staff cannot modify a requisition once submitted.")
            if user.has_group('custom_purchase.group_purchase_requisition_reviewer') and rec.state != 'submitted':
                raise UserError("Reviewers can only modify submitted requisitions.")
            if user.has_group('custom_purchase.group_purchase_requisition_approve') and rec.state != 'reviewed':
                raise UserError("Approvers can only modify reviewed requisitions.")
            if user.has_group('custom_purchase.group_purchase_requisition_authorizer') and rec.state != 'approved':
                raise UserError("Authorizers can only modify approved requisitions.")
        return super().write(vals)


    def unlink(self):
        for requestion in self:
            if requestion.state != 'draft':
                raise ValidationError(_("You cannot delete submitted requisition."))
        return super(PurchaseRequisition, self).unlink()


    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        user = self.env.user

        # Hide draft and submitted from approvers
        if user.has_group('custom_purchase.group_purchase_requisition_approve'):
            args += [('state', 'not in', ['draft', 'submitted'])]

        # Hide draft, submitted, reviewed from authorizers
        if user.has_group('custom_purchase.group_purchase_requisition_authorizer'):
            args += [('state', 'not in', ['draft', 'submitted', 'reviewed'])]

        return super().search(args, offset, limit, order, count)

    # def write(self, vals):
    #     if self.env.user.has_group('custom_purchase.group_purchase_requisition_staff'):
    #         for rec in self:
    #             if rec.state != 'draft':
    #                 raise UserError("You cannot modify a submitted requisition.")
    #     return super().write(vals)
    #
    # def search(self, args, offset=0, limit=None, order=None, count=False):
    #     if self.env.user.has_group('custom_purchase.group_purchase_requisition_approve') or \
    #             self.env.user.has_group('custom_purchase.group_purchase_requisition_authorizer'):
    #         args += [('state', 'not in', ['draft', 'submitted'])]
    #     return super(PurchaseRequisition, self).search(args, offset, limit, order, count)
    #
    # def search(self, args, offset=0, limit=None, order=None, count=False):
    #     if self.env.user.has_group('custom_purchase.group_purchase_requisition_authorizer'):
    #         args += [('state', 'not in', ['draft', 'submitted', 'reviewed'])]
    #     return super(PurchaseRequisition, self).search(args, offset, limit, order, count)
    #
    #
    #
    # def write(self, vals):
    #     if self.env.user.has_group('custom_purchase.group_purchase_requisition_reviewer'):
    #         for rec in self:
    #             if rec.state != 'submitted':
    #                 raise UserError("You cannot modify a requisition which is not in submitted state.")
    #     return super().write(vals)
    #
    # def write(self, vals):
    #     if self.env.user.has_group('custom_purchase.group_purchase_requisition_approve'):
    #         for rec in self:
    #             if rec.state != 'reviewed':
    #                 raise UserError("You cannot modify a requisition which is not in review state.")
    #     return super().write(vals)





class PurchaseRequisitionLine(models.Model):
    _name = 'purchase.requisition.custom.lines'
    _description = 'Purchase Requisition'

    item_description = fields.Many2one(comodel_name='product.template', string='Item Description', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    specifications = fields.Text(string='Specifications')
    estimated_cost = fields.Float(string='Estimated Cost')
    budget_code = fields.Char(string='Budget Code')
    justification = fields.Text(string='Justification')
    purchase_requisition_id = fields.Many2one(comodel_name="purchase.requisition.custom", string="Purchase Requisition", readonly=True,
                                required=False)
