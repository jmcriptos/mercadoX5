from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '6dc87df97a3b'
down_revision = '24981db8e03b'
branch_labels = None
depends_on = None



def column_exists(table_name, column_name):
    conn = op.get_bind()
    query = text(
        "SELECT column_name FROM information_schema.columns WHERE table_name=:table_name AND column_name=:column_name"
    )
    result = conn.execute(query, {"table_name": table_name, "column_name": column_name})

  



def upgrade():
    with op.batch_alter_table('price', schema=None) as batch_op:
        batch_op.add_column(sa.Column('presentation', sa.String(length=100), nullable=True))
        # Usando el método de verificación que definimos anteriormente
        if column_exists('price', 'presentation_id'):
            batch_op.drop_column('presentation_id')


def downgrade():
    # Como eliminaste manualmente la tabla 'presentation', debemos recrearla aquí para el downgrade.
    op.create_table(
        'presentation',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('name', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name='presentation_pkey')
    )

    with op.batch_alter_table('price', schema=None) as batch_op:
        batch_op.add_column(sa.Column('presentation_id', sa.INTEGER(), autoincrement=False, nullable=False))
        batch_op.create_foreign_key('price_presentation_id_fkey', 'presentation', ['presentation_id'], ['id'])
        batch_op.drop_column('presentation')
