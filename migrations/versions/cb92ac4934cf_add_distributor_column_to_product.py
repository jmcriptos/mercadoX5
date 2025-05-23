"""Add distributor column to Product

Revision ID: cb92ac4934cf
Revises: fa84f68ca3e0
Create Date: 2023-08-21 16:27:43.311987

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cb92ac4934cf'
down_revision = 'fa84f68ca3e0'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.add_column(sa.Column('distributor', sa.String(length=100), nullable=True))
        batch_op.drop_constraint('product_store_id_fkey', type_='foreignkey')
        batch_op.drop_column('store_id')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.add_column(sa.Column('store_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.create_foreign_key('product_store_id_fkey', 'store', ['store_id'], ['id'])
        batch_op.drop_column('distributor')

    # ### end Alembic commands ###
