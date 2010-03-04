from models import Fruit
from eav.forms import BaseDynamicEntityForm


class FruitForm(BaseDynamicEntityForm):
    model = Fruit

