{
    'name': 'Custom Purchase',
    'version': '1.0',
    'summary': 'Manage Purchase Requisitions',
    'category': 'Purchases',
    'author': 'Loomoni Morwo',
    'depends': ['purchase', 'base', 'product', 'hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'security/ir_rules.xml',
        'views/purchase_requisition_view.xml',
        'views/remove_login_brand.xml',
    ],
    'installable': True,
    'application': True,
}
